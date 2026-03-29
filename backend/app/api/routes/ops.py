from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import AIResult, ProcessingJob, RewardTransaction, ReviewDecision, VideoAsset
from app.models.enums import JobState, ReviewGate
from app.orchestrator.tasks import (
    after_review_decision_task,
    create_gate_1_task,
    create_gate_2_task,
    distribute_content_task,
    finalize_job_task,
    generate_report_task,
    handle_gate_1_task,
    issue_reward_task,
    run_phase_a_task,
)
from app.schemas.common import ApiResponse
from app.core.security import require_roles
from app.services import dlq_service, idempotency_service, policy_service


router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/metrics/admin-summary", response_model=ApiResponse)
def get_admin_summary_metrics(_user=Depends(require_roles("admin")), db: Session = Depends(get_db)):
    active_policy = policy_service.get_active_policy(db)

    videos_uploaded = db.scalar(select(func.count(VideoAsset.id))) or 0
    videos_reviewed_gate_2 = (
        db.scalar(
            select(func.count(distinct(ReviewDecision.video_id))).where(ReviewDecision.gate == ReviewGate.GATE_2)
        )
        or 0
    )
    videos_ready_to_publish = (
        db.scalar(
            select(func.count(ProcessingJob.id)).where(ProcessingJob.state == JobState.APPROVED_GATE_2)
        )
        or 0
    )
    videos_below_impact_threshold = (
        db.scalar(
            select(func.count(AIResult.id)).where(AIResult.impact_score < active_policy.threshold_p2)
        )
        or 0
    )
    rewarded_users = db.scalar(select(func.count(distinct(RewardTransaction.uploader_ref)))) or 0
    total_rewards_points = db.scalar(select(func.coalesce(func.sum(RewardTransaction.points), 0))) or 0

    return ApiResponse(
        data={
            "videos_uploaded": int(videos_uploaded),
            "videos_reviewed_gate_2": int(videos_reviewed_gate_2),
            "videos_ready_to_publish": int(videos_ready_to_publish),
            "videos_below_impact_threshold": int(videos_below_impact_threshold),
            "rewarded_users": int(rewarded_users),
            "total_rewards_points": int(total_rewards_points),
            "impact_threshold_p2": active_policy.threshold_p2,
        }
    )


@router.get("/dlq", response_model=ApiResponse)
def list_dlq(status: str | None = Query(default=None), _user=Depends(require_roles("admin")), db: Session = Depends(get_db)):
    events = dlq_service.list_dlq_events(db, status=status)
    return ApiResponse(
        data=[
            {
                "id": e.id,
                "task_name": e.task_name,
                "payload": e.payload,
                "error": e.error,
                "status": e.status,
                "created_at": e.created_at.isoformat(),
                "replayed_at": e.replayed_at.isoformat() if e.replayed_at else None,
            }
            for e in events
        ]
    )


@router.post("/dlq/{event_id}/replay", response_model=ApiResponse)
def replay_dlq_event(
    event_id: int,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    endpoint = "ops.dlq.replay"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    event = dlq_service.get_dlq_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="DLQ event not found")

    task_map = {
        "run_phase_a_task": run_phase_a_task,
        "create_gate_1_task": create_gate_1_task,
        "handle_gate_1_task": handle_gate_1_task,
        "create_gate_2_task": create_gate_2_task,
        "finalize_job_task": finalize_job_task,
        "distribute_content_task": distribute_content_task,
        "generate_report_task": generate_report_task,
        "issue_reward_task": issue_reward_task,
        "after_review_decision_task": after_review_decision_task,
    }
    task = task_map.get(event.task_name)
    if not task:
        raise HTTPException(status_code=400, detail="Unknown task for replay")

    payload = event.payload or {}
    queued = task.delay(**payload)
    dlq_service.mark_replayed(db, event.id)
    response = {"event_id": event.id, "task_id": queued.id, "replayed": True}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)
