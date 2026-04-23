from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_roles
from app.db.session import get_db
from app.models.entities import AIResult, ProcessingJob
from app.schemas.common import ApiResponse
from app.services.audio_news_service import AUDIO_NEWS_DIR
from app.services.media_composer_service import MIXED_DIR
from app.services.workflow_service import WorkflowService


router = APIRouter(prefix="/media", tags=["media"])
workflow = WorkflowService()


def _resolve_existing_path(file_path: str | None) -> Path | None:
    if not file_path:
        return None
    path = Path(file_path)
    if path.exists() and path.is_file():
        return path
    return None


def _infer_audio_path(video_id: str) -> Path | None:
    for ext in ("mp3", "wav"):
        p = AUDIO_NEWS_DIR / f"{video_id}.{ext}"
        if p.exists() and p.is_file():
            return p
    return None


def _infer_mixed_path(video_id: str) -> Path | None:
    p = MIXED_DIR / f"{video_id}_mixed.mp4"
    if p.exists() and p.is_file():
        return p
    return None


@router.get("/{video_id}/status", response_model=ApiResponse)
def get_media_status(video_id: str, _user=Depends(require_roles("moderator", "admin")), db: Session = Depends(get_db)):
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.video_id == video_id))
    ai = db.scalar(select(AIResult).where(AIResult.video_id == video_id))
    if not job or not ai:
        raise HTTPException(status_code=404, detail="Media lifecycle not found")

    audio_meta = dict((ai.generated_content or {}).get("audio_news", {}) or {})
    mix_meta = dict((ai.localized_content or {}).get("media_mix", {}) or {})

    audio_path = _resolve_existing_path(audio_meta.get("path")) or _infer_audio_path(video_id)
    mix_path = _resolve_existing_path(mix_meta.get("path")) or _infer_mixed_path(video_id)

    if audio_path and not audio_meta.get("state"):
        audio_meta["state"] = "READY"
    if audio_path:
        audio_meta["path"] = str(audio_path)
    if mix_path and not mix_meta.get("state"):
        mix_meta["state"] = "READY"
    if mix_path:
        mix_meta["path"] = str(mix_path)

    if job.state.value == "MEDIA_MIX_READY":
        if audio_path and audio_meta.get("state") != "READY":
            audio_meta["state"] = "READY"
        if mix_path and mix_meta.get("state") != "READY":
            mix_meta["state"] = "READY"

    return ApiResponse(
        data={
            "video_id": video_id,
            "job_state": job.state.value,
            "audio": audio_meta,
            "mix": mix_meta,
        }
    )


@router.post("/{video_id}/mix", response_model=ApiResponse)
def manual_mix(video_id: str, _user=Depends(require_roles("moderator", "admin")), db: Session = Depends(get_db)):
    try:
        result = workflow.retry_media_mix(db, video_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Video/job not found for mix retry")
    return ApiResponse(data={"video_id": video_id, **result})


@router.get("/{video_id}/preview/stream")
def stream_mixed_preview(video_id: str, _user=Depends(require_roles("moderator", "admin")), db: Session = Depends(get_db)):
    ai = db.scalar(select(AIResult).where(AIResult.video_id == video_id))
    if not ai:
        raise HTTPException(status_code=404, detail="AI result not found")
    mix_meta = (ai.localized_content or {}).get("media_mix", {})
    mixed_path = _resolve_existing_path(mix_meta.get("path")) or _infer_mixed_path(video_id)
    if not mixed_path:
        raise HTTPException(status_code=404, detail="Mixed preview not available")
    return FileResponse(path=str(mixed_path), media_type="video/mp4", filename=mixed_path.name)
