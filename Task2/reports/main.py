import os, time, json, base64, secrets, logging
from io import BytesIO
from datetime import datetime
from urllib.parse import quote

from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from clickhouse_driver import Client
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
import redis.asyncio as redis

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="bionic-reports")

FERNET_KEY = os.getenv("FERNET_KEY")
if not FERNET_KEY:
    raise RuntimeError("FERNET_KEY environment variable is required")
REDIS = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
CH = Client(
    host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
    port=int(os.getenv("CLICKHOUSE_PORT", 9000)),
    database=os.getenv("CLICKHOUSE_DATABASE", "bionic_analytics"),
    user=os.getenv("CLICKHOUSE_USER", "default"),
    password=os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass"),
)
COOKIE = os.getenv("SESSION_COOKIE", "bionic_session")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://localhost")
IS_PROD = os.getenv("ENV", "prod").lower() == "prod"

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

    # Ротация сессии (защита от Session Fixation)
    new_sid = secrets.token_urlsafe(32)
    await REDIS.setex(f"session:{new_sid}", 86400, raw)
    await REDIS.delete(f"session:{sid}")
    res.set_cookie(
        COOKIE, new_sid, httponly=True, secure=IS_PROD,
        samesite="lax", max_age=86400, path="/"
    )
    access_token = sess.get("access", "")
    return {"user": _parse_jwt(access_token)}


def _generate_pdf(name: str, data: dict) -> BytesIO:
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
    buf.seek(0)
    return buf


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}

@app.get("/reports/generate")
async def report(req: Request, res: Response, session: dict = Depends(_validate_session)):
    email = session["user"].get("email")
    if not email:
        return Response("Email missing in session", status_code=400)

    try:
        query = ("SELECT full_name, email, age, device_count, total_steps, "
                 "avg_battery_level, total_usage_hours, last_active_date, has_telemetry "
                 "FROM user_telemetry_mart WHERE email = %(email)s LIMIT 1")
        rows = await run_in_threadpool(
            lambda: CH.execute(query, {"email": email})
        )
    except Exception as e:
        logging.error("ClickHouse query failed: %s", e, exc_info=True)
        return Response("Database unavailable", status_code=500)

    if not rows:
        return Response("No data found for this email", status_code=200)

    cols = ["name", "email", "age", "devices", "steps", "battery", "hours", "last_active", "has_telemetry"]
    d = dict(zip(cols, rows[0]))

    pdf_data = {
        "User": d["name"] or "User",
        "Email": d["email"],
        "Age": d["age"] if d["age"] is not None else "N/A",
        "Devices": d["devices"] or 0,
        "Total Steps": f"{int(d['steps'] or 0):,}",
        "Avg Battery": f"{float(d['battery'] or 0):.1f}%",
        "Usage Hours": f"{float(d['hours'] or 0):.1f}",
        "Last Active": str(d["last_active"])[:10] if d["last_active"] else "N/A",
    }

    pdf_buf = _generate_pdf(d["name"] or "User", pdf_data)
    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''report_{quote(email, safe='')}.pdf"}
    )