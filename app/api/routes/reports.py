from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import ReportArtifact
from app.core.security import require_roles
from app.schemas.common import ApiResponse


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/video/{video_id}", response_model=ApiResponse)
def get_video_report(video_id: str, _user=Depends(require_roles("uploader", "moderator", "admin")), db: Session = Depends(get_db)):
    report = db.scalar(select(ReportArtifact).where(ReportArtifact.video_id == video_id).order_by(ReportArtifact.created_at.desc()))
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return ApiResponse(
        data={
            "video_id": report.video_id,
            "summary": report.summary,
            "storage_uri": report.storage_uri,
            "created_at": report.created_at.isoformat(),
        }
    )
