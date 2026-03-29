from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.orchestrator.celery_app import celery_app
from app.orchestrator.tasks import create_gate_1_task, create_gate_2_task, finalize_job_task, handle_gate_1_task, run_phase_a_task
from app.schemas.common import ApiResponse
from app.core.security import require_roles
from app.services import idempotency_service
from app.services.workflow_service import WorkflowService


router = APIRouter(prefix="/workflow", tags=["workflow"])
workflow = WorkflowService()


@router.post("/{job_id}/phase-a", response_model=ApiResponse)
def run_phase_a(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.phase_a"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    job = workflow.run_phase_a(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    response = {"job_id": job.job_id, "state": job.state.value, "priority": job.priority.value}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/{job_id}/phase-a/async", response_model=ApiResponse)
def run_phase_a_async(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.phase_a.async"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = run_phase_a_task.delay(job_id)
    response = {"job_id": job_id, "task_id": task.id, "queued": True}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/{job_id}/gate-1/create", response_model=ApiResponse)
def create_gate_1(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.gate1.create"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = workflow.create_gate_1_review(db, job_id)
    if not task:
        raise HTTPException(status_code=404, detail="Job not found")
    response = {"task_id": task.task_id, "gate": task.gate.value, "priority": task.priority.value}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/{job_id}/hold/escalate", response_model=ApiResponse)
def escalate_hold(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.hold.escalate"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = workflow.escalate_hold_to_gate_1(db, job_id)
    if not task:
        raise HTTPException(status_code=400, detail="Job not found or not in HOLD state")
    response = {"task_id": task.task_id, "gate": task.gate.value, "priority": task.priority.value}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/{job_id}/gate-1/create/async", response_model=ApiResponse)
def create_gate_1_async(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.gate1.create.async"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = create_gate_1_task.delay(job_id)
    response = {"job_id": job_id, "task_id": task.id, "queued": True}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/{job_id}/gate-1/handle", response_model=ApiResponse)
def handle_gate_1(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.gate1.handle"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    job = workflow.handle_gate_1_result(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    response = {"job_id": job.job_id, "state": job.state.value}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/{job_id}/gate-1/handle/async", response_model=ApiResponse)
def handle_gate_1_async(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.gate1.handle.async"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = handle_gate_1_task.delay(job_id)
    response = {"job_id": job_id, "task_id": task.id, "queued": True}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/{job_id}/gate-2/create", response_model=ApiResponse)
def create_gate_2(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.gate2.create"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = workflow.create_gate_2_review(db, job_id)
    if not task:
        raise HTTPException(status_code=404, detail="Job not found")
    response = {"task_id": task.task_id, "gate": task.gate.value, "priority": task.priority.value}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/{job_id}/gate-2/create/async", response_model=ApiResponse)
def create_gate_2_async(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.gate2.create.async"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = create_gate_2_task.delay(job_id)
    response = {"job_id": job_id, "task_id": task.id, "queued": True}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/{job_id}/finalize", response_model=ApiResponse)
def finalize(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.finalize"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    job = workflow.finalize_after_gate_2(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    response = {"job_id": job.job_id, "state": job.state.value}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.post("/{job_id}/finalize/async", response_model=ApiResponse)
def finalize_async(
    job_id: str,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("admin", "moderator")),
    db: Session = Depends(get_db),
):
    endpoint = "workflow.finalize.async"
    if x_idempotency_key:
        existing = idempotency_service.get_record(db, endpoint, x_idempotency_key)
        if existing:
            return ApiResponse(data=existing.response_json)
    task = finalize_job_task.delay(job_id)
    response = {"job_id": job_id, "task_id": task.id, "queued": True}
    if x_idempotency_key:
        idempotency_service.store_record(db, endpoint, x_idempotency_key, response)
    return ApiResponse(data=response)


@router.get("/tasks/{task_id}/status", response_model=ApiResponse)
def get_async_task_status(task_id: str, _user=Depends(require_roles("admin", "moderator"))):
    result = celery_app.AsyncResult(task_id)
    payload = result.result if isinstance(result.result, dict) else {"value": str(result.result)}
    return ApiResponse(data={"task_id": task_id, "status": result.status, "result": payload})
