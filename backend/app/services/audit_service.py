from sqlalchemy.orm import Session

from app.models.entities import AuditEvent


def write_audit(db: Session, entity_type: str, entity_id: str, event_type: str, actor_ref: str | None, payload: dict):
    event = AuditEvent(
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        actor_ref=actor_ref,
        payload=payload,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event

