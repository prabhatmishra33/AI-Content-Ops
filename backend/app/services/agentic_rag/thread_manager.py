"""
ThreadManager — assigns a story to an existing thread or creates a new one.
This is the single write path for story_threads and story_thread_links.
"""
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.pattern_entities import StoryThread, StoryThreadLink

logger = logging.getLogger(__name__)

SEVERITY_TREND_EVENT_TYPES = {"accident", "traffic", "flood", "fire", "infrastructure"}


def assign_thread(
    db: Session,
    fingerprint: dict,
    pattern_result: dict,
    ranked_result: dict,
    rag_result: dict,
) -> str:
    """
    Determine thread assignment and write to DB.
    Returns the thread_id assigned to this story.
    """
    confidence = pattern_result.get("confidence", 0.0)
    suggested_id = pattern_result.get("suggested_thread_id")
    action = pattern_result.get("suggested_thread_action", "create_new")

    # Case 1: high confidence → join existing thread
    if (
        confidence >= settings.thread_join_confidence_threshold
        and suggested_id
        and action == "join_existing"
        and _thread_exists(db, suggested_id)
    ):
        _update_thread(db, suggested_id, fingerprint, pattern_result)
        _write_link(db, fingerprint, suggested_id, pattern_result, rag_result)
        logger.info("ThreadManager: joined existing thread %s (confidence=%.2f)", suggested_id, confidence)
        return suggested_id

    # Case 2: medium confidence → create new thread linked to existing
    if (
        confidence >= settings.thread_link_confidence_threshold
        and suggested_id
        and action == "link_related"
        and _thread_exists(db, suggested_id)
    ):
        new_id = _create_thread(db, fingerprint, pattern_result)
        _write_link(db, fingerprint, new_id, pattern_result, rag_result)
        logger.info(
            "ThreadManager: created new thread %s linked to %s (confidence=%.2f)",
            new_id, suggested_id, confidence,
        )
        return new_id

    # Case 3: new standalone thread
    new_id = _create_thread(db, fingerprint, pattern_result)
    _write_link(db, fingerprint, new_id, pattern_result, rag_result)
    logger.info("ThreadManager: created new standalone thread %s", new_id)
    return new_id


# ------------------------------------------------------------------ #
# Private helpers                                                      #
# ------------------------------------------------------------------ #

def _thread_exists(db: Session, thread_id: str) -> bool:
    return db.query(StoryThread).filter_by(id=thread_id).first() is not None


def _create_thread(db: Session, fingerprint: dict, pattern_result: dict) -> str:
    now = datetime.now(timezone.utc)
    severity = fingerprint.get("severity_score")
    thread = StoryThread(
        id=str(uuid4()),
        title=_auto_title(fingerprint),
        event_type=fingerprint.get("event_type"),
        location_name=fingerprint.get("location_name"),
        location_lat=fingerprint.get("location_lat"),
        location_lng=fingerprint.get("location_lng"),
        first_story_at=now,
        last_story_at=now,
        story_count=1,
        severity_trend=[severity] if severity is not None else [],
        is_escalating=pattern_result.get("is_escalation", False),
        is_improving=pattern_result.get("is_improvement", False),
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread.id


def _update_thread(db: Session, thread_id: str, fingerprint: dict, pattern_result: dict) -> None:
    thread = db.query(StoryThread).filter_by(id=thread_id).first()
    if not thread:
        return
    thread.story_count = (thread.story_count or 0) + 1
    thread.last_story_at = datetime.now(timezone.utc)
    severity = fingerprint.get("severity_score")
    if severity is not None:
        trend = list(thread.severity_trend or [])
        trend.append(float(severity))
        thread.severity_trend = trend
        thread.is_escalating = _is_escalating(trend)
        thread.is_improving = _is_improving(trend)
    db.commit()


def _write_link(
    db: Session,
    fingerprint: dict,
    thread_id: str,
    pattern_result: dict,
    rag_result: dict,
) -> None:
    link = StoryThreadLink(
        id=str(uuid4()),
        video_id=fingerprint["video_id"],
        thread_id=thread_id,
        pattern_type=pattern_result.get("pattern_type"),
        confidence=pattern_result.get("confidence"),
        context_note=pattern_result.get("context_note"),
        is_recurrence=pattern_result.get("is_recurrence", False),
        is_escalation=pattern_result.get("is_escalation", False),
        recurrence_count=pattern_result.get("recurrence_count", 0),
        related_story_ids=pattern_result.get("related_story_ids", []),
        rag_result=rag_result,
    )
    db.add(link)
    db.commit()


def _auto_title(fingerprint: dict) -> str:
    parts = [
        fingerprint.get("event_type", "event").title(),
        "at",
        fingerprint.get("location_name") or "Unknown Location",
    ]
    return " ".join(parts)


def _is_escalating(trend: list) -> bool:
    if len(trend) < 3:
        return False
    slope = _slope(trend)
    return slope > 0.05


def _is_improving(trend: list) -> bool:
    if len(trend) < 3:
        return False
    slope = _slope(trend)
    return slope < -0.05


def _slope(values: list) -> float:
    n = len(values)
    xs = list(range(n))
    sum_x = sum(xs)
    sum_y = sum(values)
    sum_xy = sum(x * y for x, y in zip(xs, values))
    sum_x2 = sum(x * x for x in xs)
    denom = n * sum_x2 - sum_x ** 2
    return (n * sum_xy - sum_x * sum_y) / denom if denom else 0.0
