from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import require_roles
from app.db.session import get_db
from app.models.entities import DistributionResult, VideoAsset
from app.schemas.common import ApiResponse
from app.services import audit_service, distribution_service, idempotency_service, integration_service


router = APIRouter(prefix="/distribution", tags=["distribution"])


@router.get("/video/{video_id}", response_model=ApiResponse)
def get_distribution_status(
    video_id: str,
    _user=Depends(require_roles("uploader", "moderator", "admin")),
    db: Session = Depends(get_db),
):
    records = list(db.scalars(select(DistributionResult).where(DistributionResult.video_id == video_id)))
    return ApiResponse(
        data=[
            {
                "channel": r.channel,
                "external_id": r.external_id,
                "status": r.status,
                "error_reason": r.error_reason,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ]
    )


@router.get("/youtube/oauth/url", response_model=ApiResponse)
def youtube_oauth_url(
    account_ref: str = Query(default="default"),
    _user=Depends(require_roles("admin")),
):
    if not settings.youtube_client_id or not settings.youtube_redirect_uri:
        raise HTTPException(status_code=400, detail="YouTube OAuth is not configured")
    query = urlencode(
        {
            "client_id": settings.youtube_client_id,
            "redirect_uri": settings.youtube_redirect_uri,
            "response_type": "code",
            "scope": settings.youtube_oauth_scope,
            "access_type": "offline",
            "prompt": "consent",
            "state": account_ref,
        }
    )
    return ApiResponse(data={"auth_url": f"{settings.youtube_oauth_auth_url}?{query}"})


@router.get("/youtube/oauth/callback", response_model=ApiResponse)
async def youtube_oauth_callback(
    code: str,
    state: str = "default",
    x_idempotency_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    idem_key = x_idempotency_key
    endpoint = "distribution.youtube.oauth.callback"
    if idem_key:
        existing = idempotency_service.get_record(db, endpoint, idem_key)
        if existing:
            return ApiResponse(data=existing.response_json)

    token_data = await integration_service.exchange_google_code_for_tokens(code)
    expires_in = int(token_data.get("expires_in", 3600))
    expires_at_epoch = int(datetime.now(tz=timezone.utc).timestamp()) + expires_in
    integration = integration_service.upsert_integration(
        db=db,
        provider="youtube",
        account_ref=state,
        access_token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_type=token_data.get("token_type"),
        scope=token_data.get("scope"),
        expires_at_epoch=expires_at_epoch,
        metadata_json={"raw": "stored"},
    )
    response = {
        "provider": integration.provider,
        "account_ref": integration.account_ref,
        "token_saved": True,
        "expires_at_epoch": integration.expires_at_epoch,
    }
    if idem_key:
        idempotency_service.store_record(db, endpoint, idem_key, response)
    return ApiResponse(data=response)


@router.post("/youtube/publish/{video_id}", response_model=ApiResponse)
async def publish_youtube(
    video_id: str,
    account_ref: str = Query(default="default"),
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "distribution.youtube.publish"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)

    video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    result = await distribution_service.distribute_youtube(db, video.video_id, video.storage_uri, account_ref=account_ref)
    response = {
        "video_id": result.video_id,
        "channel": result.channel,
        "status": result.status,
        "external_id": result.external_id,
        "error_reason": result.error_reason,
    }
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.get("/youtube/integration/status", response_model=ApiResponse)
def youtube_integration_status(
    account_ref: str = Query(default="default"),
    _user=Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    integ = integration_service.get_integration(db, provider="youtube", account_ref=account_ref)
    if not integ:
        return ApiResponse(data={"connected": False, "account_ref": account_ref})
    return ApiResponse(
        data={
            "connected": True,
            "provider": integ.provider,
            "account_ref": integ.account_ref,
            "expires_at_epoch": integ.expires_at_epoch,
            "has_refresh_token": bool(integ.refresh_token),
        }
    )


@router.get("/youtube/quota", response_model=ApiResponse)
def youtube_quota(_user=Depends(require_roles("admin")), db: Session = Depends(get_db)):
    usage = integration_service.get_provider_quota_usage(db, provider="youtube")
    return ApiResponse(data=usage)


@router.get("/youtube/status/{external_id}", response_model=ApiResponse)
async def youtube_status(
    external_id: str,
    account_ref: str = Query(default="default"),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    status = await distribution_service.poll_youtube_status(db, external_id, account_ref=account_ref)
    return ApiResponse(data={"external_id": external_id, **status})


@router.post("/youtube/webhook", response_model=ApiResponse)
async def youtube_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if settings.youtube_webhook_secret and x_webhook_secret != settings.youtube_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    payload = await request.json()
    video_id = str(payload.get("video_id", "unknown"))
    event_type = str(payload.get("event_type", "YOUTUBE_WEBHOOK"))
    audit_service.write_audit(
        db,
        "distribution",
        video_id,
        event_type,
        "youtube_webhook",
        payload,
    )
    return ApiResponse(data={"received": True, "video_id": video_id, "event_type": event_type})
