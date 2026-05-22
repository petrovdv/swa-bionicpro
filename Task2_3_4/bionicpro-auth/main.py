import os, time, secrets, base64, json, logging

from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from authlib.integrations.httpx_client import AsyncOAuth2Client
import redis.asyncio as redis
import httpx

logger = logging.getLogger("bionicpro-auth")
app = FastAPI(title="bionicpro-auth")

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://localhost")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
REALM = os.getenv("KEYCLOAK_REALM", "reports-realm")
CLIENT_ID = os.getenv("CLIENT_ID", "reports-frontend")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
SESSION_COOKIE = "bionic_session"
REDIRECT_URI = os.getenv("AUTH_CALLBACK_URL", "https://localhost/auth/callback")
IS_DEV = os.getenv("ENV", "prod").lower() != "prod"
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SESSION_TTL = 86400  # 24 часа

_raw_key    = os.getenv("FERNET_KEY")
FERNET_KEY  = _raw_key.encode() if _raw_key else Fernet.generate_key()
if not _raw_key:
    logger.warning("FERNET_KEY не задан — используется случайный ключ. "
                   "После рестарта refresh-токены станут невалидными.")
fernet = Fernet(FERNET_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Session-Rotated-Id"],
)

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

TOKEN_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"

def encrypt_refresh(token: str) -> str:
    if not token:
        return ""
    return fernet.encrypt(token.encode()).decode()

def decrypt_refresh(token: str) -> str:
    if not token:
        return ""
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        logger.error(
            "Не удалось расшифровать refresh-токен: невалидный шифротекст или неверный ключ")
        raise HTTPException(401, detail="Session invalid")

async def _get_session(sid: str) -> dict | None:
    try:
        data = await redis_client.get(f"session:{sid}")
        return json.loads(data) if data else None
    except Exception:
        logger.exception("Redis: ошибка чтения сессии sid=%s", sid)
        return None

async def _save_session(sid: str, data: dict):
    try:
        await redis_client.setex(f"session:{sid}", SESSION_TTL, json.dumps(data))
    except Exception:
        logger.exception("Redis: ошибка сохранения сессии sid=%s", sid)

async def _delete_session(sid: str):
    try:
        await redis_client.delete(f"session:{sid}")
    except Exception:
        logger.exception("Redis: ошибка удаления сессии sid=%s", sid)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code:
        raise HTTPException(400, detail="Missing auth code")

    code_verifier = base64.b64decode(state).decode() if state else None

    async with AsyncOAuth2Client(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET or None,
        redirect_uri=REDIRECT_URI,
        code_challenge_method="S256" if code_verifier else None,
        timeout=httpx.Timeout(10),
    ) as client:
        token = await client.fetch_token(
            url=TOKEN_URL,
            authorization_response=str(request.url),
            code_verifier=code_verifier,
        )

    sid = secrets.token_urlsafe(32)
    await _save_session(sid, {
        "access": token["access_token"],
        "refresh": encrypt_refresh(token.get("refresh_token", "")),
        "expires_at": time.time() + token.get("expires_in", 120),
    })

    redirect_response = RedirectResponse(
        url=f"{FRONTEND_URL}/?auth=success",
        status_code=302
    )

    redirect_response.set_cookie(
        SESSION_COOKIE, sid, httponly=True, secure=not IS_DEV,
        samesite="lax", max_age=SESSION_TTL, path="/"
    )
    return redirect_response

@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        await _delete_session(sid)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "logged_out"}

async def require_session(request: Request, response: Response) -> dict:
    sid = request.cookies.get(SESSION_COOKIE)
    sess = await _get_session(sid) if sid else None

    if not sess:
        raise HTTPException(401, detail="Unauthorized")

    # Автообновление access_token (за 30 сек до истечения)
    if time.time() >= sess["expires_at"] - 30 and sess["refresh"]:
        try:
            async with AsyncOAuth2Client(
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET or None,
                    token={"refresh_token": decrypt_refresh(sess["refresh"])},
                    timeout=httpx.Timeout(10),
            ) as client:
                new_token = await client.refresh_token(url=TOKEN_URL)

            sess.update({
                "access": new_token["access_token"],
                "refresh": encrypt_refresh(
                    new_token.get("refresh_token") or decrypt_refresh(sess["refresh"])
                ),
                "expires_at": time.time() + new_token.get("expires_in", 120),
            })
            await _save_session(sid, sess)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Ошибка обновления access_token для sid=%s", sid)
            raise HTTPException(401, detail="Token refresh failed")

    # Ротация сессии (защита от Session Fixation)
    new_sid = secrets.token_urlsafe(32)
    await _save_session(new_sid, sess)
    await _delete_session(sid)

    response.set_cookie(
        SESSION_COOKIE, new_sid, httponly=True, secure=not IS_DEV,
        samesite="lax", max_age=SESSION_TTL, path="/",
    )
    response.headers["X-Session-Rotated-Id"] = new_sid
    return sess

@app.get("/auth/data")
async def protected_route(sess: dict = Depends(require_session)):
    return {"message": "Secure data", "token_preview": sess["access"][:20] + "..." + sess["access"][-20:]}

@app.get("/auth/status")
async def status(request: Request):
    sid = request.cookies.get(SESSION_COOKIE)
    sess = await _get_session(sid) if sid else None
    return {"authenticated": sess is not None}
