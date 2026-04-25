"""
Tool 3 — search_by_person
Finds past stories involving named individuals using Postgres array overlap.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_PERSON_SQL = """
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
    ARRAY(
        SELECT unnest(nf.persons_involved)
        INTERSECT
        SELECT unnest(CAST(:person_names AS text[]))
    ) AS matched_persons
FROM news_fingerprints nf
WHERE
    nf.persons_involved && CAST(:person_names AS text[])
    AND nf.published_epoch > :min_epoch
    AND nf.video_id != :exclude_video_id
ORDER BY nf.published_at DESC
LIMIT :limit
"""


def search_by_person(
    db: Session,
    *,
    video_id: str,
    person_names: list[str],
    days_back: int = 180,
    limit: int = 10,
) -> dict:
    if not person_names:
        return {"stories": [], "matched_persons": [], "search_type": "person"}

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    min_epoch = now_epoch - (days_back * 86400)

    # Normalise to lowercase (consistent with CorrelationAgent)
    names_lower = [n.lower().strip() for n in person_names if n.strip()]
    # Postgres array literal: {"name one","name two"}
    pg_array = "{" + ",".join(f'"{n}"' for n in names_lower) + "}"

    try:
        rows = db.execute(
            text(_PERSON_SQL),
            {
                "person_names": pg_array,
                "min_epoch": min_epoch,
                "exclude_video_id": video_id,
                "limit": limit,
            },
        ).fetchall()
    except Exception as exc:
        logger.error("search_by_person failed: %s", exc)
        return {"stories": [], "matched_persons": [], "search_type": "person"}

    all_matched: set[str] = set()
    stories = []
    for row in rows:
        matched = list(row.matched_persons or [])
        all_matched.update(matched)
        stories.append(_row_to_candidate(row, matched_persons=matched))

    return {
        "stories": stories,
        "matched_persons": list(all_matched),
        "search_type": "person",
    }


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
