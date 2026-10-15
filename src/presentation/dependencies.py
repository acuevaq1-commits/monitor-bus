import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.infrastructure.database.session import monitor_session
from src.infrastructure.settings import get_settings


def period(hours: int = 24):
    hours = max(1, min(hours, 720))
    end = datetime.now(timezone.utc)
    return end - timedelta(hours=hours), end


def current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(401, "Inicie sesión")
    return user


def current_web_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_role(role: str):
    ranks = {"consulta": 0, "operador": 1, "analista": 2, "administrador": 3}
    def dependency(user=Depends(current_user)):
        if ranks.get(user.get("role", ""), -1) < ranks[role]:
            raise HTTPException(403, "Permiso insuficiente")
        return user
    return dependency


def verify_login(username: str, password: str):
    settings = get_settings()
    return not admin_setup_required() and hmac.compare_digest(username, settings.admin_user) and hmac.compare_digest(password, settings.admin_password)


def admin_setup_required():
    return get_settings().admin_password in {"", "CAMBIAR_CLAVE_ADMIN", "replace-with-a-strong-password"}


def check_csrf(request: Request, token: str):
    expected = request.session.get("csrf", "")
    if not expected or not hmac.compare_digest(expected, token):
        raise HTTPException(403, "CSRF inválido")


def new_csrf():
    return secrets.token_urlsafe(32)
