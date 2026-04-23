from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import ProcessingJob
from app.models.enums import PriorityQueue, ReviewDecisionValue, ReviewGate
from app.orchestrator.tasks import after_review_decision_task
from app.schemas.common import ApiResponse
from app.core.security import require_roles
from app.schemas.review import ReviewDecisionRequest
from app.services import audit_service, idempotency_service, review_service
from app.services.workflow_service import WorkflowService


router = APIRouter(prefix="/reviews", tags=["reviews"])
workflow = WorkflowService()


@router.get("/tasks", response_model=ApiResponse)
def list_tasks(
    gate: ReviewGate | None = Query(default=None),
    status: str | None = Query(default=None),
    _user=Depends(require_roles("moderator", "admin")),
    db: Session = Depends(get_db),
):
    tasks = review_service.list_review_tasks(db, gate=gate, status=status)
    return ApiResponse(
        data=[
            {
                "task_id": t.task_id,
                "job_id": t.job_id,
                "video_id": t.video_id,
                "gate": t.gate.value,
                "priority": t.priority.value,
                "status": t.status,
                "reviewer_ref": t.reviewer_ref,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]
    )


@router.post("/tasks/{task_id}/decision", response_model=ApiResponse)
def submit_decision(
    task_id: str,
    payload: ReviewDecisionRequest,
    auto_progress: bool = Query(default=True),
    async_mode: bool = Query(default=True),
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("moderator", "admin")),
    db: Session = Depends(get_db),
):
    endpoint = f"reviews.decision:{task_id}"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    try:
        decision_enum = ReviewDecisionValue(payload.decision.upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid decision. Use APPROVE or REJECT.") from exc

    decision = review_service.submit_review_decision(
        db=db,
        task_id=task_id,
        reviewer_ref=payload.reviewer_ref,
        decision=decision_enum,
        notes=payload.notes,
    )
    if not decision:
        raise HTTPException(status_code=404, detail="Task not found")
    task = review_service.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    audit_service.write_audit(
        db,
        "review_task",
        task.task_id,
        "REVIEW_DECISION_SUBMITTED",
        payload.reviewer_ref,
        {
            "job_id": task.job_id,
            "video_id": task.video_id,
            "gate": decision.gate.value,
            "decision": decision.decision.value,
            "notes": payload.notes,
        },
    )
    audit_service.write_audit(
        db,
        "job",
        task.job_id,
        f"{decision.gate.value}_DECISION_{decision.decision.value}",
        payload.reviewer_ref,
        {
            "task_id": task.task_id,
            "video_id": task.video_id,
            "gate": decision.gate.value,
            "decision": decision.decision.value,
            "notes": payload.notes,
        },
    )

    next_actions: list[str] = []
    if auto_progress:
        if async_mode:
            queued = after_review_decision_task.delay(task.job_id, decision.gate.value, decision.decision.value)
            next_actions.append(f"async_task_enqueued:{queued.id}")
        else:
            if decision.gate == ReviewGate.GATE_1:
                workflow.handle_gate_1_result(db, task.job_id)
                if decision.decision == ReviewDecisionValue.APPROVE:
                    job = db.query(ProcessingJob).filter(ProcessingJob.job_id == task.job_id).first()
                    if job and job.state.value == "MEDIA_MIX_READY":
                        workflow.create_gate_2_review(db, task.job_id)
                        next_actions.append("gate_2_created")
                    else:
                        next_actions.append("gate_2_not_created_media_mix_not_ready")
                else:
                    next_actions.append("job_rejected_gate_1")
            elif decision.gate == ReviewGate.GATE_2:
                workflow.finalize_after_gate_2(db, task.job_id)
                next_actions.append("finalize_triggered")

    response = {
        "task_id": decision.task_id,
        "video_id": decision.video_id,
        "gate": decision.gate.value,
        "decision": decision.decision.value,
        "auto_progress": auto_progress,
        "async_mode": async_mode,
        "next_actions": next_actions,
    }
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/tasks/{task_id}/claim", response_model=ApiResponse)
def claim_task(
    task_id: str,
    reviewer_ref: str = Query(...),
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("moderator", "admin")),
    db: Session = Depends(get_db),
):
    endpoint = f"reviews.claim:{task_id}"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = review_service.claim_task(db, task_id, reviewer_ref)
    if not task:
        raise HTTPException(status_code=400, detail="Task not claimable")
    response = {"task_id": task.task_id, "status": task.status, "reviewer_ref": task.reviewer_ref}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/tasks/{task_id}/release", response_model=ApiResponse)
def release_task(
    task_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("moderator", "admin")),
    db: Session = Depends(get_db),
):
    endpoint = f"reviews.release:{task_id}"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = review_service.release_task(db, task_id)
    if not task:
        raise HTTPException(status_code=400, detail="Task not releasable")
    response = {"task_id": task.task_id, "status": task.status}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/tasks/{task_id}/escalate", response_model=ApiResponse)
def escalate_task(
    task_id: str,
    to_priority: PriorityQueue = Query(...),
    escalated_by: str = Query(...),
    reason: str = Query(...),
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    endpoint = f"reviews.escalate:{task_id}"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    esc = review_service.escalate_task(db, task_id, to_priority, escalated_by, reason)
    if not esc:
        raise HTTPException(status_code=404, detail="Task not found")
    response = {
        "task_id": esc.task_id,
        "from_priority": esc.from_priority,
        "to_priority": esc.to_priority,
        "reason": esc.reason,
        "escalated_by": esc.escalated_by,
    }
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/tasks/{task_id}/reopen", response_model=ApiResponse)
def reopen_task(
    task_id: str,
    reviewer_ref: str = Query(...),
    notes: str | None = Query(default=None),
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = f"reviews.reopen:{task_id}"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = review_service.reopen_task(db, task_id, reviewer_ref, notes)
    if not task:
        raise HTTPException(status_code=400, detail="Task not reopenable")
    response = {"task_id": task.task_id, "status": task.status}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.get("/sla/breaches", response_model=ApiResponse)
def sla_breaches(_user=Depends(require_roles("admin", "moderator")), db: Session = Depends(get_db)):
    tasks = review_service.list_sla_breaches(db)
    return ApiResponse(
        data=[
            {
                "task_id": t.task_id,
                "job_id": t.job_id,
                "gate": t.gate.value,
                "priority": t.priority.value,
                "status": t.status,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]
    )
