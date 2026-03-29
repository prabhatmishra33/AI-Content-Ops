from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import DeadLetterEvent


def add_dlq_event(db: Session, task_name: str, payload: dict, error: str) -> DeadLetterEvent:
    event = DeadLetterEvent(task_name=task_name, payload=payload, error=error, status="NEW")
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_dlq_events(db: Session, status: str | None = None) -> list[DeadLetterEvent]:
    stmt = select(DeadLetterEvent).order_by(DeadLetterEvent.created_at.desc())
    if status:
        stmt = stmt.where(DeadLetterEvent.status == status)
    return list(db.scalars(stmt))


def get_dlq_event(db: Session, event_id: int) -> DeadLetterEvent | None:
    return db.scalar(select(DeadLetterEvent).where(DeadLetterEvent.id == event_id))


def mark_replayed(db: Session, event_id: int) -> DeadLetterEvent | None:
    event = db.scalar(select(DeadLetterEvent).where(DeadLetterEvent.id == event_id))
    if not event:
        return None
    event.status = "REPLAYED"
    event.replayed_at = datetime.utcnow()
    db.commit()
    db.refresh(event)
    return event
