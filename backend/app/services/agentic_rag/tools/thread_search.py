"""
Tool 6 — search_by_thread
Retrieves the full ordered history of a known story thread.
Only called when RouterAgent has identified a specific thread_id.
"""
import logging

from sqlalchemy.orm import Session

from app.models.pattern_entities import NewsFingerprint, StoryThread

logger = logging.getLogger(__name__)


def search_by_thread(
    db: Session,
    *,
    thread_id: str,
    limit: int = 20,
) -> dict:
    thread = db.query(StoryThread).filter_by(id=thread_id).first()
    if not thread:
        return {"thread": None, "stories": [], "search_type": "thread"}

    records = (
        db.query(NewsFingerprint)
        .filter_by(thread_id=thread_id)
        .order_by(NewsFingerprint.published_at.desc())
        .limit(limit)
        .all()
    )

    stories = [_record_to_candidate(r) for r in records]
    thread_dict = {
        "id": thread.id,
        "title": thread.title,
        "event_type": thread.event_type,
        "location_name": thread.location_name,
        "story_count": thread.story_count,
        "is_escalating": thread.is_escalating,
        "is_improving": thread.is_improving,
        "first_story_at": thread.first_story_at.isoformat() if thread.first_story_at else None,
        "last_story_at": thread.last_story_at.isoformat() if thread.last_story_at else None,
        "severity_trend": [float(s) for s in (thread.severity_trend or [])],
    }
    return {"thread": thread_dict, "stories": stories, "search_type": "thread"}


def _record_to_candidate(record: NewsFingerprint) -> dict:
    return {
        "story_id": record.video_id,
        "summary": record.summary,
        "event_type": record.event_type,
        "location_name": record.location_name,
        "location_lat": float(record.location_lat) if record.location_lat else None,
        "location_lng": float(record.location_lng) if record.location_lng else None,
        "persons_involved": record.persons_involved or [],
        "severity_score": float(record.severity_score) if record.severity_score else 0.0,
        "published_at": record.published_at.isoformat() if record.published_at else None,
        "published_epoch": record.published_epoch or 0,
        "keywords": record.keywords or [],
        "thread_id": record.thread_id,
    }
