from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UploadCompleteRequest(BaseModel):
    uploader_ref: str = Field(..., min_length=2)
    filename: str
    content_type: str = "video/mp4"
    storage_uri: Optional[str] = None
    idempotency_key: Optional[str] = None


class VideoResponse(BaseModel):
    video_id: str
    uploader_ref: str
    filename: str
    content_type: str
    storage_uri: Optional[str]
    thumbnail_uri: Optional[str] = None
    created_at: datetime


class JobStatusResponse(BaseModel):
    job_id: str
    video_id: str
    state: str
    priority: str
    attempts: int
    last_error: Optional[str]
    updated_at: datetime
