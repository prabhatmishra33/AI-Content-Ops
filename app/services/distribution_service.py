from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import asyncio
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import DistributionResult
from app.services import integration_service


def _record_distribution(db: Session, video_id: str, channel: str, status: str, external_id: Optional[str], error_reason: Optional[str]):
    record = DistributionResult(
        video_id=video_id,
        channel=channel,
        external_id=external_id,
        status=status,
        error_reason=error_reason,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


async def distribute_youtube(db: Session, video_id: str, storage_uri: Optional[str], account_ref: str = "default") -> DistributionResult:
    if not integration_service.consume_quota(db, "youtube", settings.youtube_daily_quota_limit):
        return _record_distribution(db, video_id, "youtube", "FAILED", None, "youtube-daily-quota-exceeded")

    token = await integration_service.get_valid_youtube_access_token(db, account_ref=account_ref)
    if not token:
        if settings.youtube_strict_mode:
            return _record_distribution(db, video_id, "youtube", "FAILED", None, "missing-youtube-oauth-token")
        return _record_distribution(
            db,
            video_id,
            "youtube",
            "MOCK_SUCCESS",
            f"yt_mock_{video_id}_{int(datetime.utcnow().timestamp())}",
            "youtube-token-not-configured-fallback",
        )

    file_path: Optional[Path] = Path(storage_uri) if storage_uri else None
    if not file_path or not file_path.exists():
        return _record_distribution(db, video_id, "youtube", "FAILED", None, "storage-file-not-found")

    metadata = {
        "snippet": {
            "title": f"AI Content Ops - {video_id}",
            "description": "Published by AI Content Ops backend pipeline",
            "tags": ["ai", "contentops", "mvp"],
            "categoryId": "22",
        },
        "status": {"privacyStatus": settings.youtube_publish_default_visibility},
    }

    upload_url = f"{settings.youtube_api_upload_url}?uploadType=resumable&part=snippet,status"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(file_path.stat().st_size),
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            init_res = await client.post(upload_url, headers=headers, json=metadata)
            init_res.raise_for_status()
            session_url = init_res.headers.get("Location")
            if not session_url:
                return _record_distribution(db, video_id, "youtube", "FAILED", None, "youtube-resumable-session-missing")

            data = file_path.read_bytes()
            put_headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(len(data)),
            }
            upload_res = await client.put(session_url, headers=put_headers, content=data)
            upload_res.raise_for_status()
            payload = upload_res.json()
            external_id = payload.get("id")
            return _record_distribution(db, video_id, "youtube", "SUCCESS", external_id, None)
    except Exception as exc:
        return _record_distribution(db, video_id, "youtube", "FAILED", None, str(exc))


async def poll_youtube_status(db: Session, external_id: str, account_ref: str = "default") -> dict:
    token = await integration_service.get_valid_youtube_access_token(db, account_ref=account_ref)
    if not token:
        return {"status": "UNKNOWN", "error": "missing-youtube-token"}
    params = {"part": "status,processingDetails", "id": external_id}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(settings.youtube_status_poll_url, headers=headers, params=params)
            res.raise_for_status()
            payload = res.json()
            items = payload.get("items", [])
            if not items:
                return {"status": "NOT_FOUND", "error": None}
            item = items[0]
            upload_status = item.get("status", {}).get("uploadStatus", "unknown")
            privacy = item.get("status", {}).get("privacyStatus", "unknown")
            processing = item.get("processingDetails", {}).get("processingStatus", "unknown")
            return {"status": "SUCCESS", "upload_status": upload_status, "privacy_status": privacy, "processing_status": processing}
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc)}


def _secondary_payload(video_id: str) -> dict:
    return {
        "video_id": video_id,
        "event": "publish",
        "timestamp_utc": datetime.utcnow().isoformat(),
    }


async def distribute_secondary(db: Session, video_id: str) -> DistributionResult:
    url = settings.secondary_channel_webhook_url
    if not url:
        if settings.secondary_channel_strict_mode:
            return _record_distribution(db, video_id, "secondary", "FAILED", None, "secondary-webhook-not-configured")
        return _record_distribution(
            db=db,
            video_id=video_id,
            channel="secondary",
            status="MOCK_SUCCESS",
            external_id=f"sec_mock_{video_id}_{int(datetime.utcnow().timestamp())}",
            error_reason="secondary-webhook-not-configured-fallback",
        )

    headers = {"Content-Type": "application/json"}
    if settings.secondary_channel_api_key:
        headers["Authorization"] = f"Bearer {settings.secondary_channel_api_key}"
    payload = _secondary_payload(video_id)
    last_error: Optional[str] = None
    for attempt in range(1, settings.secondary_channel_retry_max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.secondary_channel_timeout_seconds) as client:
                res = await client.post(url, headers=headers, json=payload)
                res.raise_for_status()
                external_id = f"sec_{video_id}_{int(datetime.utcnow().timestamp())}"
                return _record_distribution(db, video_id, "secondary", "SUCCESS", external_id, None)
        except Exception as exc:
            last_error = str(exc)
            if attempt < settings.secondary_channel_retry_max_attempts:
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
    return _record_distribution(db, video_id, "secondary", "FAILED", None, last_error or "unknown-secondary-error")
