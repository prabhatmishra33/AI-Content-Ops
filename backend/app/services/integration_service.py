from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import IntegrationCredential, IntegrationQuotaUsage


def _now_epoch() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())


def _now_day_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _get_fernet() -> Fernet | None:
    if not settings.token_encryption_key:
        return None
    return Fernet(settings.token_encryption_key.encode())


def _enc(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    f = _get_fernet()
    if not f:
        return value
    return f.encrypt(value.encode()).decode()


def _dec(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    f = _get_fernet()
    if not f:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        # Backward compatibility with plaintext tokens.
        return value


def get_integration(db: Session, provider: str, account_ref: str = "default") -> Optional[IntegrationCredential]:
    return db.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.provider == provider,
            IntegrationCredential.account_ref == account_ref,
        )
    )


def upsert_integration(
    db: Session,
    provider: str,
    account_ref: str,
    access_token: Optional[str],
    refresh_token: Optional[str],
    token_type: Optional[str],
    scope: Optional[str],
    expires_at_epoch: Optional[int],
    metadata_json: Optional[dict] = None,
) -> IntegrationCredential:
    integ = get_integration(db, provider, account_ref)
    if not integ:
        integ = IntegrationCredential(provider=provider, account_ref=account_ref)
        db.add(integ)
    integ.access_token = _enc(access_token)
    integ.refresh_token = _enc(refresh_token)
    integ.token_type = token_type
    integ.scope = scope
    integ.expires_at_epoch = expires_at_epoch
    if metadata_json is not None:
        integ.metadata_json = metadata_json
    db.commit()
    db.refresh(integ)
    return integ


def consume_quota(db: Session, provider: str, limit_count: int) -> bool:
    day = _now_day_utc()
    usage = db.scalar(
        select(IntegrationQuotaUsage).where(
            IntegrationQuotaUsage.provider == provider,
            IntegrationQuotaUsage.day_utc == day,
        )
    )
    if not usage:
        usage = IntegrationQuotaUsage(provider=provider, day_utc=day, used_count=0, limit_count=limit_count)
        db.add(usage)
        db.flush()
    usage.limit_count = limit_count
    if usage.used_count >= usage.limit_count:
        db.commit()
        return False
    usage.used_count += 1
    db.commit()
    return True


def get_provider_quota_usage(db: Session, provider: str) -> dict:
    day = _now_day_utc()
    usage = db.scalar(
        select(IntegrationQuotaUsage).where(
            IntegrationQuotaUsage.provider == provider,
            IntegrationQuotaUsage.day_utc == day,
        )
    )
    if not usage:
        return {"provider": provider, "day_utc": day, "used_count": 0, "limit_count": 0, "remaining": 0}
    remaining = max(usage.limit_count - usage.used_count, 0)
    return {
        "provider": usage.provider,
        "day_utc": usage.day_utc,
        "used_count": usage.used_count,
        "limit_count": usage.limit_count,
        "remaining": remaining,
    }


async def exchange_google_code_for_tokens(code: str) -> dict:
    if not settings.youtube_client_id or not settings.youtube_client_secret or not settings.youtube_redirect_uri:
        raise ValueError("Missing YouTube OAuth config in environment")
    payload = {
        "code": code,
        "client_id": settings.youtube_client_id,
        "client_secret": settings.youtube_client_secret,
        "redirect_uri": settings.youtube_redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(settings.youtube_token_url, data=payload)
        res.raise_for_status()
        return res.json()


async def refresh_google_access_token(refresh_token: str) -> dict:
    payload = {
        "client_id": settings.youtube_client_id,
        "client_secret": settings.youtube_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(settings.youtube_token_url, data=payload)
        res.raise_for_status()
        return res.json()


async def get_valid_youtube_access_token(db: Session, account_ref: str = "default") -> Optional[str]:
    integ = get_integration(db, "youtube", account_ref)
    if not integ:
        return None
    access_token = _dec(integ.access_token)
    refresh_token = _dec(integ.refresh_token)
    if access_token and integ.expires_at_epoch and integ.expires_at_epoch > (_now_epoch() + 60):
        return access_token
    if not refresh_token:
        return access_token
    token_data = await refresh_google_access_token(refresh_token)
    expires_in = int(token_data.get("expires_in", 3600))
    integ.access_token = _enc(token_data.get("access_token"))
    integ.token_type = token_data.get("token_type")
    integ.scope = token_data.get("scope", integ.scope)
    integ.expires_at_epoch = _now_epoch() + expires_in
    db.commit()
    db.refresh(integ)
    return _dec(integ.access_token)
