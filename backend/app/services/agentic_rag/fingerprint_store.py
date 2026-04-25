"""
FingerprintStore — read/write layer for news_fingerprints table on pattern DB.
"""
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.pattern_entities import NewsFingerprint

logger = logging.getLogger(__name__)


class FingerprintStore:

    @staticmethod
    def upsert(db: Session, video_id: str, fingerprint: dict) -> NewsFingerprint:
        """
        Insert a new fingerprint or update the existing one for this video_id.
        The rag_result and thread_id fields are NOT overwritten here —
        they are set later by ThreadManager.
        """
        existing = db.query(NewsFingerprint).filter_by(video_id=video_id).first()

        published_at = fingerprint.get("published_at")
        if isinstance(published_at, str):
            try:
                published_at = datetime.fromisoformat(published_at)
            except ValueError:
                published_at = datetime.now(timezone.utc)
        elif published_at is None:
            published_at = datetime.now(timezone.utc)

        if existing:
            existing.event_type = fingerprint.get("event_type", existing.event_type)
            existing.summary = fingerprint.get("summary", existing.summary)
            existing.location_raw = fingerprint.get("location_raw", existing.location_raw)
            existing.location_name = fingerprint.get("location_name", existing.location_name)
            existing.location_lat = fingerprint.get("location_lat", existing.location_lat)
            existing.location_lng = fingerprint.get("location_lng", existing.location_lng)
            existing.location_confidence = fingerprint.get("location_confidence", existing.location_confidence)
            existing.persons_involved = fingerprint.get("persons_involved", existing.persons_involved) or []
            existing.severity_score = fingerprint.get("severity_score", existing.severity_score)
            existing.severity_label = fingerprint.get("severity_label", existing.severity_label)
            existing.keywords = fingerprint.get("keywords", existing.keywords) or []
            existing.embedding = fingerprint.get("embedding", existing.embedding)
            existing.published_at = published_at
            existing.published_epoch = fingerprint.get(
                "published_epoch", int(published_at.timestamp())
            )
            db.commit()
            db.refresh(existing)
            logger.info("FingerprintStore: updated fingerprint for video_id=%s", video_id)
            return existing

        record = NewsFingerprint(
            id=str(uuid4()),
            video_id=video_id,
            event_type=fingerprint.get("event_type", "other"),
            summary=fingerprint.get("summary"),
            location_raw=fingerprint.get("location_raw"),
            location_name=fingerprint.get("location_name"),
            location_lat=fingerprint.get("location_lat"),
            location_lng=fingerprint.get("location_lng"),
            location_confidence=fingerprint.get("location_confidence"),
            persons_involved=fingerprint.get("persons_involved") or [],
            severity_score=fingerprint.get("severity_score"),
            severity_label=fingerprint.get("severity_label"),
            keywords=fingerprint.get("keywords") or [],
            embedding=fingerprint.get("embedding"),
            published_at=published_at,
            published_epoch=fingerprint.get("published_epoch", int(published_at.timestamp())),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info("FingerprintStore: inserted fingerprint for video_id=%s", video_id)
        return record

    @staticmethod
    def get_by_video_id(db: Session, video_id: str) -> NewsFingerprint | None:
        return db.query(NewsFingerprint).filter_by(video_id=video_id).first()

    @staticmethod
    def get_rag_result(db: Session, video_id: str) -> dict | None:
        record = db.query(NewsFingerprint).filter_by(video_id=video_id).first()
        return record.rag_result if record else None

    @staticmethod
    def set_rag_result(db: Session, video_id: str, rag_result: dict, thread_id: str | None = None) -> bool:
        record = db.query(NewsFingerprint).filter_by(video_id=video_id).first()
        if not record:
            return False
        record.rag_result = rag_result
        if thread_id:
            record.thread_id = thread_id
        db.commit()
        return True
