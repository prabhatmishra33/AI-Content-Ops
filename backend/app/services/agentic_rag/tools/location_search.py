"""
Tool 1 — search_by_location_and_event
Finds past stories of the same event type within a geographic radius.
Uses Haversine formula in a CTE — no PostGIS required.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session



logger = logging.getLogger(__name__)

# CTE avoids recalculating the distance expression twice
_HAVERSINE_SQL = """
WITH candidates AS (
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
        (
            6371000 * 2 * ASIN(
                SQRT(
                    POWER(SIN(RADIANS(nf.location_lat - :lat) / 2), 2) +
                    COS(RADIANS(:lat)) * COS(RADIANS(nf.location_lat)) *
                    POWER(SIN(RADIANS(nf.location_lng - :lng) / 2), 2)
                )
            )
        ) AS distance_meters
    FROM news_fingerprints nf
    WHERE
        nf.event_type = :event_type
        AND nf.published_epoch > :min_epoch
        AND nf.location_lat IS NOT NULL
        AND nf.location_lng IS NOT NULL
        AND nf.video_id != :exclude_video_id
)
SELECT * FROM candidates
WHERE distance_meters <= :radius_meters
ORDER BY published_at DESC
LIMIT :limit
"""


def search_by_location_and_event(
    db: Session,
    *,
    video_id: str,
    event_type: str,
    lat: float,
    lng: float,
    radius_meters: int = 500,
    days_back: int = 90,
    limit: int = 15,
) -> dict:
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    min_epoch = now_epoch - (days_back * 86400)

    try:
        rows = db.execute(
            text(_HAVERSINE_SQL),
            {
                "event_type": event_type,
                "lat": lat,
                "lng": lng,
                "radius_meters": radius_meters,
                "min_epoch": min_epoch,
                "exclude_video_id": video_id,
                "limit": limit,
            },
        ).fetchall()
    except Exception as exc:
        logger.error("search_by_location_and_event failed: %s", exc)
        return {"stories": [], "search_type": "location_and_event"}

    stories = [_row_to_candidate(row, distance_meters=float(row.distance_meters)) for row in rows]
    return {"stories": stories, "search_type": "location_and_event"}


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
