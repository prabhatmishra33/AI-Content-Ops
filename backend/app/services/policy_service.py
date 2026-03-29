from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import ThresholdPolicy


def get_active_policy(db: Session) -> ThresholdPolicy:
    policy = db.scalar(select(ThresholdPolicy).where(ThresholdPolicy.is_active.is_(True)).order_by(ThresholdPolicy.created_at.desc()))
    if policy:
        return policy

    # Bootstrap default policy row
    policy = ThresholdPolicy(
        version="v1-default",
        threshold_p0=settings.threshold_p0,
        threshold_p1=settings.threshold_p1,
        threshold_p2=settings.threshold_p2,
        hold_auto_create_gate1=settings.hold_auto_create_gate1,
        is_active=True,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def activate_new_policy(
    db: Session,
    version: str,
    threshold_p0: float,
    threshold_p1: float,
    threshold_p2: float,
    hold_auto_create_gate1: bool,
) -> ThresholdPolicy:
    db.execute(update(ThresholdPolicy).values(is_active=False))
    new_policy = ThresholdPolicy(
        version=version,
        threshold_p0=threshold_p0,
        threshold_p1=threshold_p1,
        threshold_p2=threshold_p2,
        hold_auto_create_gate1=hold_auto_create_gate1,
        is_active=True,
    )
    db.add(new_policy)
    db.commit()
    db.refresh(new_policy)
    return new_policy

