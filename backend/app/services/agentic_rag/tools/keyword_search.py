"""
Tool 5 — search_by_keyword
Full-text keyword search using Postgres array overlap.
Used as fallback when location is unavailable.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_KEYWORD_SQL = """
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
    array_length(
        ARRAY(
            SELECT unnest(nf.keywords)
            INTERSECT
            SELECT unnest(CAST(:keywords AS text[]))
        ),
        1
    ) AS keyword_overlap_count
FROM news_fingerprints nf
WHERE
    nf.keywords && CAST(:keywords AS text[])
    AND (:event_type IS NULL OR nf.event_type = :event_type)
    AND nf.published_epoch > :min_epoch
    AND nf.video_id != :exclude_video_id
HAVING
    array_length(
        ARRAY(
            SELECT unnest(nf.keywords)
            INTERSECT
            SELECT unnest(CAST(:keywords AS text[]))
        ),
        1
    ) >= :match_threshold
ORDER BY keyword_overlap_count DESC, nf.published_at DESC
LIMIT :limit
"""


def search_by_keyword(
    db: Session,
    *,
    video_id: str,
    keywords: list[str],
    event_type: str | None = None,
    days_back: int = 90,
    limit: int = 15,
    match_threshold: int = 2,
) -> dict:
    if not keywords:
        return {"stories": [], "search_type": "keyword"}

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    min_epoch = now_epoch - (days_back * 86400)

    kw_lower = [k.lower().strip() for k in keywords if k.strip()]
    pg_array = "{" + ",".join(f'"{k}"' for k in kw_lower) + "}"

    try:
        rows = db.execute(
            text(_KEYWORD_SQL),
            {
                "keywords": pg_array,
                "event_type": event_type,
                "min_epoch": min_epoch,
                "exclude_video_id": video_id,
                "match_threshold": match_threshold,
                "limit": limit,
            },
        ).fetchall()
    except Exception as exc:
        logger.error("search_by_keyword failed: %s", exc)
        return {"stories": [], "search_type": "keyword"}

    stories = [
        _row_to_candidate(row, keyword_overlap=int(row.keyword_overlap_count or 0))
        for row in rows
    ]
    return {"stories": stories, "search_type": "keyword"}


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
