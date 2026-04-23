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
            "updated_at": ai.updated_at.isoformat(),
        }
    )
