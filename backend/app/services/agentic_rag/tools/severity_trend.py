"""
Tool 4 — get_severity_trend
Returns ordered severity scores for a location over time and computes the trend.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_TREND_SQL = """
WITH candidates AS (
    SELECT
        nf.video_id AS story_id,
        nf.published_at,
        nf.published_epoch,
        nf.severity_score,
        nf.summary,
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
SELECT story_id, published_at, published_epoch, severity_score, summary
FROM candidates
WHERE distance_meters <= :radius_meters
ORDER BY published_at ASC
"""


def get_severity_trend(
    db: Session,
    *,
    video_id: str,
    event_type: str,
    lat: float,
    lng: float,
    radius_meters: int = 500,
    days_back: int = 90,
) -> dict:
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    min_epoch = now_epoch - (days_back * 86400)

    try:
        rows = db.execute(
            text(_TREND_SQL),
            {
                "event_type": event_type,
                "lat": lat,
                "lng": lng,
                "radius_meters": radius_meters,
                "min_epoch": min_epoch,
                "exclude_video_id": video_id,
            },
        ).fetchall()
    except Exception as exc:
        logger.error("get_severity_trend failed: %s", exc)
        return _insufficient_result()

    if len(rows) < 2:
        return _insufficient_result()

    data_points = [
        {
            "story_id": row.story_id,
            "published_at": row.published_at.isoformat() if row.published_at else None,
            "severity_score": float(row.severity_score) if row.severity_score else 0.0,
            "summary": row.summary,
        }
        for row in rows
    ]

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    points_xy = [
        {
            "x": (now_epoch - (row.published_epoch or now_epoch)) / 86400,  # days_ago
            "y": float(row.severity_score) if row.severity_score else 0.0,
        }
        for row in rows
    ]

    slope = _linear_slope(points_xy)
    first_score = points_xy[0]["y"]
    last_score = points_xy[-1]["y"]
    change_pct = ((last_score - first_score) / first_score * 100) if first_score else 0.0

    n = len(rows)
    if slope > 0.05 and n >= 3:
        direction = "escalating"
    elif slope < -0.05 and n >= 3:
        direction = "improving"
    else:
        direction = "stable"

    return {
        "data_points": data_points,
        "trend_direction": direction,
        "trend_slope": round(slope, 4),
        "severity_change_pct": round(change_pct, 1),
        "search_type": "severity_trend",
    }


def _linear_slope(points: list[dict]) -> float:
    n = len(points)
    if n < 2:
        return 0.0
    sum_x = sum(p["x"] for p in points)
    sum_y = sum(p["y"] for p in points)
    sum_xy = sum(p["x"] * p["y"] for p in points)
    sum_x2 = sum(p["x"] ** 2 for p in points)
    denom = n * sum_x2 - sum_x ** 2
    return (n * sum_xy - sum_x * sum_y) / denom if denom else 0.0


def _insufficient_result() -> dict:
    return {
        "data_points": [],
        "trend_direction": "insufficient_data",
        "trend_slope": 0.0,
        "severity_change_pct": 0.0,
        "search_type": "severity_trend",
    }
