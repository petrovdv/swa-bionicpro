import os, time, json, base64, secrets, logging
from contextlib import asynccontextmanager
from io import BytesIO
from datetime import datetime

from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from clickhouse_driver import Client
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
import redis.asyncio as redis
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)

ROTATION_INTERVAL = 300  # ротация не чаще раза в 5 минут
MART_TABLE = os.getenv("MART_TABLE_NAME", "user_telemetry_mart_cdc")

COOKIE       = os.getenv("SESSION_COOKIE", "bionic_session")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://localhost")
IS_PROD      = os.getenv("ENV", "prod").lower() == "prod"
S3_BUCKET    = os.getenv("S3_BUCKET", "reports")
S3_ENDPOINT  = os.getenv("S3_ENDPOINT", "http://minio:9000")
CDN_BASE_URL = os.getenv("CDN_BASE_URL", "https://localhost/cdn")

REDIS = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
CH = Client(
    host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
    port=int(os.getenv("CLICKHOUSE_PORT", 9000)),
    database=os.getenv("CLICKHOUSE_DB", "bionic_analytics"),
    user=os.getenv("CLICKHOUSE_USER", "default"),
    password=os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass"),
    send_receive_timeout=30,
)
s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=os.getenv("MINIO_ROOT_USER", "minioadmin"),
    aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD", "minioadmin"),
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(_ensure_bucket)
    try:
        CH.execute("SELECT 1")
        logging.info("ClickHouse connection OK")
    except Exception as e:
        logging.warning("ClickHouse not ready at startup: %s", e)
    yield


app = FastAPI(title="bionic-reports", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Session-Rotated-Id"],
)


def _parse_jwt(token: str) -> dict:
    """Безопасное извлечение payload из JWT без проверки подписи (для внутренней сети)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT structure")
        payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.b64decode(payload))
    except Exception as e:
        logging.warning("JWT parse failed: %s", e)
        return {}

async def _validate_session(req: Request, res: Response) -> dict:
    """Проверка Redis-сессии, ротация ID, возврат данных пользователя."""
    sid = req.cookies.get(COOKIE)
    if not sid:
        raise HTTPException(401, "Missing session cookie")

    raw = await REDIS.get(f"session:{sid}")
    sess = json.loads(raw) if raw else None
    if not sess or time.time() >= sess.get("expires_at", 0):
        raise HTTPException(401, "Session expired or invalid")

    # Ротируем только если прошло достаточно времени
    last_rotated = sess.get("last_rotated", 0)
    if time.time() - last_rotated >= ROTATION_INTERVAL:
        new_sid = secrets.token_urlsafe(32)
        sess["last_rotated"] = time.time()
        new_raw = json.dumps(sess)

        await REDIS.setex(f"session:{new_sid}", 86400, new_raw)
        await REDIS.delete(f"session:{sid}")

        res.set_cookie(
            COOKIE, new_sid, httponly=True, secure=IS_PROD,
            samesite="lax", max_age=86400, path="/"
        )
        res.headers["X-Session-Rotated-Id"] = new_sid

    # Если ротация не нужна — cookie не трогаем, старый sid продолжает работать
    return {"user": _parse_jwt(sess.get("access", ""))}


def _s3_key(email: str) -> str:
    """Ключ объекта: reports/{email}/{YYYY-MM-DD}.pdf.
    Дата в имени файла обеспечивает ежедневное обновление без явной инвалидации кеша.
    """
    return f"{email}/{datetime.now().strftime('%Y-%m-%d')}.pdf"

def _cdn_url(key: str) -> str:
    return f"{CDN_BASE_URL}/{key}"


def _s3_object_exists(key: str) -> bool:
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def _ensure_bucket() -> None:
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=S3_BUCKET)
        logging.info("Created S3 bucket: %s", S3_BUCKET)
    # Разрешаем публичное чтение — Nginx обращается к MinIO без авторизации
    policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": "*"},
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{S3_BUCKET}/*",
        }],
    })
    s3.put_bucket_policy(Bucket=S3_BUCKET, Policy=policy)


def _generate_pdf(name: str, data: dict) -> bytes:
    """Генерация PDF-отчёта с автопереносом страниц."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _, h = A4

    c.setFont("Helvetica-Bold", 18)
    c.drawString(2 * cm, h - 2.5 * cm, f"Report: {name}")
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, h - 3.5 * cm, f"Date: {datetime.now():%d.%m.%Y %H:%M}")

    y = h - 5 * cm
    for k, v in data.items():
        if y < 3 * cm:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = h - 3 * cm
        c.drawString(2.5 * cm, y, f"{k}: {v}")
        y -= 0.7 * cm

    c.save()
    return buf.getvalue()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/reports/generate")
async def report(req: Request, res: Response, session: dict = Depends(_validate_session)):
    email = session["user"].get("email")
    if not email:
        return Response("Email missing in session", status_code=400)

    key = _s3_key(email)

    # Проверяем наличие готового отчёта в S3
    if await run_in_threadpool(_s3_object_exists, key):
        logging.info("Report cache hit for %s: %s", email, key)
        return JSONResponse({"url": _cdn_url(key)})

    # Отчёт не найден — генерируем
    try:
        query = (f"SELECT full_name, email, age, device_count, total_steps, "
                 "avg_battery_level, total_usage_hours, last_active_date, has_telemetry "
                 f"FROM {MART_TABLE} FINAL WHERE email = %(email)s LIMIT 1")
        rows = await run_in_threadpool(lambda: CH.execute(query, {"email": email}))
    except Exception as e:
        logging.error("ClickHouse query failed: %s", e, exc_info=True)
        return Response("Database unavailable", status_code=500)

    if not rows:
        return Response("No data found for this email", status_code=200)

    cols = ["name", "email", "age", "devices", "steps", "battery", "hours", "last_active", "has_telemetry"]
    d = dict(zip(cols, rows[0]))

    pdf_data = {
        "User":        d["name"] or "User",
        "Email":       d["email"],
        "Age":         d["age"] if d["age"] is not None else "N/A",
        "Devices":     d["devices"] or 0,
        "Total Steps": f"{int(d['steps'] or 0):,}",
        "Avg Battery": f"{float(d['battery'] or 0):.1f}%",
        "Usage Hours": f"{float(d['hours'] or 0):.1f}",
        "Last Active": str(d["last_active"])[:10] if d["last_active"] else "N/A",
    }

    pdf_bytes = _generate_pdf(d["name"] or "User", pdf_data)
    await run_in_threadpool(
        lambda: s3.put_object(Bucket=S3_BUCKET, Key=key, Body=pdf_bytes, ContentType="application/pdf")
    )
    logging.info("Report saved to S3: %s", key)

    return JSONResponse({"url": _cdn_url(key)})