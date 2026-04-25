"""
Tool 2 — search_by_semantic_similarity
Finds conceptually similar past stories using pgvector cosine similarity.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_SEMANTIC_SQL = """
SELECT
    nf.id,
    nf.video_id,
    nf.event_type,
    nf.summary,
    nf.location_name,
    nf.location_lat,
    nf.location_lng,
    nf.persons_involved,
    nf.severity_score,
    nf.published_at,
    nf.published_epoch,
    nf.keywords,
    nf.thread_id,
    1 - (nf.embedding <=> CAST(:embedding AS vector)) AS similarity_score
FROM news_fingerprints nf
WHERE
    nf.published_epoch > :min_epoch
    AND (:event_type IS NULL OR nf.event_type = :event_type)
    AND nf.embedding IS NOT NULL
    AND nf.video_id != :exclude_video_id
    AND 1 - (nf.embedding <=> CAST(:embedding AS vector)) > :min_score
ORDER BY nf.embedding <=> CAST(:embedding AS vector)
LIMIT :limit
"""


def search_by_semantic_similarity(
    db: Session,
    *,
    video_id: str,
    embedding: list[float],
    min_score: float = 0.72,
    days_back: int = 90,
    event_type: str | None = None,
    limit: int = 20,
) -> dict:
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    min_epoch = now_epoch - (days_back * 86400)

    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    try:
        rows = db.execute(
            text(_SEMANTIC_SQL),
            {
                "embedding": embedding_str,
                "min_score": min_score,
                "min_epoch": min_epoch,
                "event_type": event_type,
                "exclude_video_id": video_id,
                "limit": limit,
            },
        ).fetchall()
    except Exception as exc:
        logger.error("search_by_semantic_similarity failed: %s", exc)
        return {"stories": [], "search_type": "semantic"}

    stories = [
        _row_to_candidate(row, raw_similarity_score=float(row.similarity_score))
        for row in rows
    ]
    return {"stories": stories, "search_type": "semantic"}


def _row_to_candidate(row, **extra) -> dict:
    return {
        "story_id": row.video_id,
        "summary": row.summary,
        "event_type": row.event_type,
        "location_name": row.location_name,
        "location_lat": float(row.location_lat) if row.location_lat else None,
        "location_lng": float(row.location_lng) if row.location_lng else None,
        "persons_involved": row.persons_involved or [],
        "severity_score": float(row.severity_score) if row.severity_score else 0.0,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "published_epoch": row.published_epoch or 0,
        "keywords": row.keywords or [],
        "thread_id": row.thread_id,
        **extra,
    }
