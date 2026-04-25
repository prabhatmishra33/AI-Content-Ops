"""
Scorer — computes final_score for each CandidateStory and tags pattern signals.
All weights are configurable via settings (no magic numbers).
"""
import logging
import math
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)


def score_and_rank(
    candidates: list[dict],
    fingerprint: dict,
    severity_trend: dict | None,
) -> dict:
    """
    Score, tag, sort, and cap candidates.

    Returns a RankedResult dict.
    """
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    escalating = (
        severity_trend is not None
        and severity_trend.get("trend_direction") == "escalating"
    )

    for c in candidates:
        _score_candidate(c, fingerprint, now_epoch)
        _tag_signals(c, fingerprint, escalating)

    candidates.sort(key=lambda c: c.get("final_score", 0.0), reverse=True)
    top = candidates[: settings.top_k_to_synthesiser]

    recurrence_count = sum(
        1 for c in top if "recurrence" in (c.get("pattern_signals") or [])
    )
    highest = top[0]["final_score"] if top else 0.0

    return {
        "top_candidates": top,
        "severity_trend": severity_trend,
        "recurrence_count": recurrence_count,
        "highest_score": round(highest, 4),
        "search_types_used": [],  # filled by pipeline.py
    }


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

def _score_candidate(candidate: dict, fingerprint: dict, now_epoch: int) -> None:
    days_ago = (now_epoch - (candidate.get("published_epoch") or now_epoch)) / 86400
    temporal_weight = math.exp(-settings.temporal_decay_lambda * days_ago)

    semantic_score = candidate.get("raw_similarity_score") or 0.0

    new_entities = [
        *[p.lower() for p in fingerprint.get("persons_involved", [])],
        (fingerprint.get("location_name") or "").lower(),
        (fingerprint.get("event_type") or "").lower(),
    ]
    cand_entities = [
        *[p.lower() for p in candidate.get("persons_involved", [])],
        (candidate.get("location_name") or "").lower(),
        (candidate.get("event_type") or "").lower(),
    ]
    overlap = sum(1 for e in new_entities if e and e in cand_entities)
    entity_overlap = min(overlap / max(len(new_entities), 1), 1.0)

    proximity_bonus = (
        settings.score_proximity_bonus
        if (candidate.get("distance_meters") or float("inf")) < 500
        else 0.0
    )
    person_bonus = (
        settings.score_person_bonus
        if (candidate.get("matched_persons") or [])
        else 0.0
    )

    raw_score = (
        settings.score_weight_semantic * semantic_score
        + settings.score_weight_entity * entity_overlap
        + settings.score_weight_temporal * temporal_weight
        + proximity_bonus
        + person_bonus
    )

    candidate["temporal_weight"] = round(temporal_weight, 4)
    candidate["entity_overlap"] = round(entity_overlap, 4)
    candidate["final_score"] = round(min(raw_score, 1.0), 4)


def _tag_signals(candidate: dict, fingerprint: dict, escalating: bool) -> None:
    signals: list[str] = list(candidate.get("pattern_signals") or [])

    if (
        candidate.get("event_type") == fingerprint.get("event_type")
        and (candidate.get("distance_meters") or float("inf")) < 500
    ):
        _add(signals, "recurrence")

    if candidate.get("matched_persons"):
        _add(signals, "same_person")

    if candidate.get("thread_id"):
        _add(signals, "existing_thread")

    if escalating:
        _add(signals, "escalation")

    candidate["pattern_signals"] = signals


def _add(lst: list, item: str) -> None:
    if item not in lst:
        lst.append(item)
