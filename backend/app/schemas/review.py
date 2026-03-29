from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ReviewDecisionRequest(BaseModel):
    reviewer_ref: str
    decision: str
    notes: Optional[str] = None


class ReviewTaskResponse(BaseModel):
    task_id: str
    job_id: str
    video_id: str
    gate: str
    priority: str
    status: str
    reviewer_ref: Optional[str]
    created_at: datetime

