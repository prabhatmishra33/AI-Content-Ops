from pydantic import BaseModel, Field


class PolicyUpsertRequest(BaseModel):
    version: str = Field(..., min_length=2)
    threshold_p0: float = Field(..., ge=0.0, le=1.0)
    threshold_p1: float = Field(..., ge=0.0, le=1.0)
    threshold_p2: float = Field(..., ge=0.0, le=1.0)
    hold_auto_create_gate1: bool = False

