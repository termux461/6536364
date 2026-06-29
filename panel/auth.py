from itsdangerous import BadSignature, URLSafeTimedSerializer
from fastapi import Cookie, HTTPException

from config import settings

_serializer = URLSafeTimedSerializer(settings.PANEL_SECRET_KEY, salt="panel-auth")
COOKIE_NAME = "panel_session"
MAX_AGE = 60 * 60 * 12


def create_session_token() -> str:
    return _serializer.dumps({"admin": True})


def verify_credentials(login: str, password: str) -> bool:
    return login == settings.PANEL_ADMIN_LOGIN and password == settings.PANEL_ADMIN_PASSWORD


async def require_admin(panel_session: str | None = Cookie(default=None)) -> bool:
    if not panel_session:
        raise HTTPException(status_code=303, headers={"Location": "/panel/login"})
    try:
        data = _serializer.loads(panel_session, max_age=MAX_AGE)
    except BadSignature:
        raise HTTPException(status_code=303, headers={"Location": "/panel/login"})
    if not data.get("admin"):
        raise HTTPException(status_code=303, headers={"Location": "/panel/login"})
    return True
