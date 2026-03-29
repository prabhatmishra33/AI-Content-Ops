from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ReviewDecision, ReviewEscalation, ReviewTask
from app.models.enums import PriorityQueue, ReviewDecisionValue, ReviewGate


def create_review_task(db: Session, job_id: str, video_id: str, gate: ReviewGate, priority: str) -> ReviewTask:
    existing = db.scalar(
        select(ReviewTask).where(
            ReviewTask.job_id == job_id,
            ReviewTask.gate == gate,
            ReviewTask.status.in_(["PENDING", "IN_PROGRESS"]),
        )
    )
    if existing:
        return existing
    task = ReviewTask(
        task_id=f"task_{uuid4().hex[:10]}",
        job_id=job_id,
        video_id=video_id,
        gate=gate,
        priority=priority,
        status="PENDING",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_review_tasks(db: Session, gate: ReviewGate | None = None, status: str | None = None):
    stmt = select(ReviewTask)
    if gate:
        stmt = stmt.where(ReviewTask.gate == gate)
    if status:
        stmt = stmt.where(ReviewTask.status == status)
    return list(db.scalars(stmt.order_by(ReviewTask.created_at.desc())))


def get_task_by_id(db: Session, task_id: str) -> ReviewTask | None:
    return db.scalar(select(ReviewTask).where(ReviewTask.task_id == task_id))


def claim_task(db: Session, task_id: str, reviewer_ref: str) -> ReviewTask | None:
    task = get_task_by_id(db, task_id)
    if not task or task.status != "PENDING":
        return None
    task.status = "IN_PROGRESS"
    task.reviewer_ref = reviewer_ref
    db.commit()
    db.refresh(task)
    return task


def release_task(db: Session, task_id: str) -> ReviewTask | None:
    task = get_task_by_id(db, task_id)
    if not task or task.status not in {"IN_PROGRESS", "PENDING"}:
        return None
    task.status = "PENDING"
    task.reviewer_ref = None
    db.commit()
    db.refresh(task)
    return task


def reopen_task(db: Session, task_id: str, reviewer_ref: str, notes: str | None) -> ReviewTask | None:
    task = get_task_by_id(db, task_id)
    if not task or task.status != "DONE":
        return None
    task.status = "PENDING"
    task.reviewer_ref = None
    if notes:
        dec = ReviewDecision(
            task_id=task.task_id,
            video_id=task.video_id,
            gate=task.gate,
            decision=ReviewDecisionValue.REJECT,
            reviewer_ref=reviewer_ref,
            notes=f"REOPEN_NOTE: {notes}",
            created_at=datetime.utcnow(),
        )
        db.add(dec)
    db.commit()
    db.refresh(task)
    return task


def escalate_task(
    db: Session,
    task_id: str,
    to_priority: PriorityQueue,
    escalated_by: str,
    reason: str,
) -> ReviewEscalation | None:
    task = get_task_by_id(db, task_id)
    if not task:
        return None
    from_priority = task.priority.value
    task.priority = to_priority
    esc = ReviewEscalation(
        task_id=task.task_id,
        from_priority=from_priority,
        to_priority=to_priority.value,
        reason=reason,
        escalated_by=escalated_by,
    )
    db.add(esc)
    db.commit()
    db.refresh(esc)
    return esc


def _sla_minutes(priority: PriorityQueue) -> int:
    if priority == PriorityQueue.P0:
        return 10
    if priority == PriorityQueue.P1:
        return 30
    if priority == PriorityQueue.P2:
        return 120
    return 360


def list_sla_breaches(db: Session) -> list[ReviewTask]:
    tasks = list(db.scalars(select(ReviewTask).where(ReviewTask.status.in_(["PENDING", "IN_PROGRESS"]))))
    now = datetime.utcnow()
    breached = []
    for task in tasks:
        due = task.created_at + timedelta(minutes=_sla_minutes(task.priority))
        if now > due:
            breached.append(task)
    return breached


def submit_review_decision(
    db: Session, task_id: str, reviewer_ref: str, decision: ReviewDecisionValue, notes: str | None
) -> ReviewDecision | None:
    task = db.scalar(select(ReviewTask).where(ReviewTask.task_id == task_id))
    if not task:
        return None
    task.status = "DONE"
    task.reviewer_ref = reviewer_ref
    dec = ReviewDecision(
        task_id=task_id,
        video_id=task.video_id,
        gate=task.gate,
        decision=decision,
        reviewer_ref=reviewer_ref,
        notes=notes,
        created_at=datetime.utcnow(),
    )
    db.add(dec)
    db.commit()
    db.refresh(dec)
    return dec
