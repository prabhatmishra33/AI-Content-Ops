from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import require_roles
from app.schemas.common import ApiResponse
from app.schemas.policy import PolicyUpsertRequest
from app.services import idempotency_service, policy_service


router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("/active", response_model=ApiResponse)
def get_active_policy(_user=Depends(require_roles("admin", "moderator")), db: Session = Depends(get_db)):
    policy = policy_service.get_active_policy(db)
    return ApiResponse(
        data={
            "version": policy.version,
            "threshold_p0": policy.threshold_p0,
            "threshold_p1": policy.threshold_p1,
            "threshold_p2": policy.threshold_p2,
            "impact_confidence_min": policy.impact_confidence_min,
            "news_trending_escalation_enabled": policy.news_trending_escalation_enabled,
            "hold_auto_create_gate1": policy.hold_auto_create_gate1,
            "is_active": policy.is_active,
        }
    )


@router.post("/activate", response_model=ApiResponse)
def activate_policy(
    payload: PolicyUpsertRequest,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    endpoint = "policies.activate"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    policy = policy_service.activate_new_policy(
        db=db,
        version=payload.version,
        threshold_p0=payload.threshold_p0,
        threshold_p1=payload.threshold_p1,
        threshold_p2=payload.threshold_p2,
        impact_confidence_min=payload.impact_confidence_min,
        news_trending_escalation_enabled=payload.news_trending_escalation_enabled,
        hold_auto_create_gate1=payload.hold_auto_create_gate1,
    )
    response = {
        "version": policy.version,
        "threshold_p0": policy.threshold_p0,
        "threshold_p1": policy.threshold_p1,
        "threshold_p2": policy.threshold_p2,
        "impact_confidence_min": policy.impact_confidence_min,
        "news_trending_escalation_enabled": policy.news_trending_escalation_enabled,
        "hold_auto_create_gate1": policy.hold_auto_create_gate1,
        "is_active": policy.is_active,
    }
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)
