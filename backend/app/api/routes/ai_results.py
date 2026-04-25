from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import AIResult
from app.core.security import require_roles
from app.schemas.common import ApiResponse


router = APIRouter(prefix="/ai-results", tags=["ai-results"])


@router.get("/video/{video_id}", response_model=ApiResponse)
def get_ai_result(video_id: str, _user=Depends(require_roles("moderator", "admin")), db: Session = Depends(get_db)):
    ai = db.scalar(select(AIResult).where(AIResult.video_id == video_id))
    if not ai:
        raise HTTPException(status_code=404, detail="AI result not found")
    generated_content = ai.generated_content or {}
    localized_content = ai.localized_content or {}
    audio_meta = generated_content.get("audio_news", {}) if isinstance(generated_content, dict) else {}
    mix_meta = localized_content.get("media_mix", {}) if isinstance(localized_content, dict) else {}
    content_prep_done = bool(generated_content) and bool(localized_content)
    media_mix_ready = str(mix_meta.get("state", "")).upper() == "READY"
    phase_b_overall = "COMPLETED" if content_prep_done and media_mix_ready else ("IN_PROGRESS" if content_prep_done else "NOT_STARTED")
    return ApiResponse(
        data={
            "video_id": ai.video_id,
            "moderation_flags": ai.moderation_flags,
            "tags": ai.tags,
            "impact_score": ai.impact_score,
            "compliance": ai.compliance,
            "generated_content": generated_content,
            "localized_content": localized_content,
            "audio_news": generated_content.get("audio_news", {}),
            "media_mix": localized_content.get("media_mix", {}),
            "phase_b": {
                "content_prep_status": "COMPLETED" if content_prep_done else "NOT_STARTED",
                "media_mix_status": "COMPLETED" if media_mix_ready else ("IN_PROGRESS" if content_prep_done else "NOT_STARTED"),
                "overall_status": phase_b_overall,
                "audio_state": audio_meta.get("state", "PENDING") if isinstance(audio_meta, dict) else "PENDING",
                "media_mix_state": mix_meta.get("state", "PENDING") if isinstance(mix_meta, dict) else "PENDING",
            },
            "updated_at": ai.updated_at.isoformat(),
        }
    )
