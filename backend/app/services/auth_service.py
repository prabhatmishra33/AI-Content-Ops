from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings


@dataclass
class AuthUser:
    username: str
    role: str


def _user_store() -> dict[str, tuple[str, str]]:
    return {
        settings.auth_default_admin_username: (settings.auth_default_admin_password, "admin"),
        settings.auth_default_moderator_username: (settings.auth_default_moderator_password, "moderator"),
        settings.auth_default_uploader_username: (settings.auth_default_uploader_password, "uploader"),
    }


def authenticate_user(username: str, password: str) -> AuthUser | None:
    users = _user_store()
    row = users.get(username)
    if not row:
        return None
    pwd, role = row
    if password != pwd:
        return None
    return AuthUser(username=username, role=role)


def create_access_token(user: AuthUser) -> str:
    now = datetime.now(tz=timezone.utc)
    exp = now + timedelta(minutes=settings.auth_access_token_exp_minutes)
    payload = {
        "sub": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)


def decode_access_token(token: str) -> AuthUser:
    payload = jwt.decode(token, settings.auth_jwt_secret, algorithms=[settings.auth_jwt_algorithm])
    return AuthUser(username=payload["sub"], role=payload["role"])

