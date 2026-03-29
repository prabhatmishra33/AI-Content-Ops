from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import IdempotencyRecord


def get_record(db: Session, endpoint: str, idempotency_key: str) -> IdempotencyRecord | None:
    return db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.endpoint == endpoint,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )


def store_record(db: Session, endpoint: str, idempotency_key: str, response_json: dict) -> IdempotencyRecord:
    rec = IdempotencyRecord(endpoint=endpoint, idempotency_key=idempotency_key, response_json=response_json)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec

