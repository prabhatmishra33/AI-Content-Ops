"""
Patterns API — exposes AgenticRAG results to the frontend.

GET /api/v1/patterns/stories/{video_id}/patterns   — full RAG result for a story
GET /api/v1/patterns/stories/{video_id}/context    — just the context_note (for quick UI use)
GET /api/v1/patterns/threads                       — list all active story threads
GET /api/v1/patterns/threads/{thread_id}           — full thread detail
GET /api/v1/patterns/threads/{thread_id}/stories   — all stories in a thread
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.pattern_session import get_pattern_db, is_pattern_db_available
from app.models.pattern_entities import NewsFingerprint, StoryThread, StoryThreadLink
from app.services.agentic_rag.fingerprint_store import FingerprintStore

router = APIRouter(prefix="/patterns", tags=["patterns"])


def _require_pattern_db(db: Session = Depends(get_pattern_db)) -> Session:
    return db


@router.get("/stories/{video_id}/patterns")
def get_story_patterns(video_id: str, db: Session = Depends(_require_pattern_db)):
    """Full AgenticRAGResult for a story."""
    record = FingerprintStore.get_by_video_id(db, video_id)
    if not record:
        raise HTTPException(status_code=404, detail="No fingerprint found for this story")
    return {
        "video_id": video_id,
        "fingerprint": _fingerprint_summary(record),
        "rag_result": record.rag_result,
    }


@router.get("/stories/{video_id}/context")
def get_story_context(video_id: str, db: Session = Depends(_require_pattern_db)):
    """Just the editor context note — fast endpoint for review page."""
    rag = FingerprintStore.get_rag_result(db, video_id)
    if not rag:
        return {"video_id": video_id, "context_note": None, "available": False}
    return {
        "video_id": video_id,
        "context_note": rag.get("context_note"),
        "pattern_type": rag.get("pattern_type"),
        "confidence": rag.get("confidence"),
        "is_recurrence": rag.get("is_recurrence"),
        "is_escalation": rag.get("is_escalation"),
        "recurrence_count": rag.get("recurrence_count"),
        "thread_id": rag.get("thread_id"),
        "available": True,
    }


@router.get("/threads")
def list_threads(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(_require_pattern_db),
):
    """List active story threads, newest first."""
    threads = (
        db.query(StoryThread)
        .order_by(StoryThread.last_story_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"threads": [_thread_summary(t) for t in threads], "total": len(threads)}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str, db: Session = Depends(_require_pattern_db)):
    """Full thread detail including severity trend."""
    thread = db.query(StoryThread).filter_by(id=thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return _thread_detail(thread)


@router.get("/threads/{thread_id}/stories")
def get_thread_stories(
    thread_id: str,
    limit: int = 20,
    db: Session = Depends(_require_pattern_db),
):
    """All stories in a thread, newest first."""
    links = (
        db.query(StoryThreadLink)
        .filter_by(thread_id=thread_id)
        .order_by(StoryThreadLink.created_at.desc())
        .limit(limit)
        .all()
    )
    stories = []
    for link in links:
        fp = FingerprintStore.get_by_video_id(db, link.video_id)
        stories.append({
            "video_id": link.video_id,
            "pattern_type": link.pattern_type,
            "confidence": float(link.confidence) if link.confidence else None,
            "context_note": link.context_note,
            "is_recurrence": link.is_recurrence,
            "is_escalation": link.is_escalation,
            "recurrence_count": link.recurrence_count,
            "published_at": fp.published_at.isoformat() if fp and fp.published_at else None,
            "severity_score": float(fp.severity_score) if fp and fp.severity_score else None,
            "location_name": fp.location_name if fp else None,
            "summary": fp.summary if fp else None,
        })
    return {"thread_id": thread_id, "stories": stories}


# ------------------------------------------------------------------ #
# Serialisation helpers                                                #
# ------------------------------------------------------------------ #

def _fingerprint_summary(record: NewsFingerprint) -> dict:
    return {
        "event_type": record.event_type,
        "location_name": record.location_name,
        "severity_score": float(record.severity_score) if record.severity_score else None,
        "severity_label": record.severity_label,
        "summary": record.summary,
        "persons_involved": record.persons_involved or [],
        "keywords": record.keywords or [],
        "published_at": record.published_at.isoformat() if record.published_at else None,
        "thread_id": record.thread_id,
    }


def _thread_summary(thread: StoryThread) -> dict:
    return {
        "id": thread.id,
        "title": thread.title,
        "event_type": thread.event_type,
        "location_name": thread.location_name,
        "story_count": thread.story_count,
        "is_escalating": thread.is_escalating,
        "is_improving": thread.is_improving,
        "last_story_at": thread.last_story_at.isoformat() if thread.last_story_at else None,
    }


def _thread_detail(thread: StoryThread) -> dict:
    d = _thread_summary(thread)
    d["first_story_at"] = thread.first_story_at.isoformat() if thread.first_story_at else None
    d["severity_trend"] = [float(s) for s in (thread.severity_trend or [])]
    d["location_lat"] = float(thread.location_lat) if thread.location_lat else None
    d["location_lng"] = float(thread.location_lng) if thread.location_lng else None
    return d
