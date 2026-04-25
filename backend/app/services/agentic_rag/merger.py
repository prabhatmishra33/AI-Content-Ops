"""
Merger — deduplicates CandidateStory results from multiple tools.
When the same story_id appears in multiple tool results, signal fields are merged
by taking the strongest signal (max similarity, min distance, union of persons).
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def merge_results(tool_results: list[dict]) -> list[dict]:
    """
    Flatten all tool results into a single deduplicated list of CandidateStory dicts.
    """
    pool: dict[str, dict] = {}

    for result in tool_results:
        for story in result.get("stories", []):
            sid = story.get("story_id")
            if not sid:
                continue
            if sid not in pool:
                pool[sid] = dict(story)
                pool[sid].setdefault("pattern_signals", [])
            else:
                pool[sid] = _merge_candidate(pool[sid], story)

    return list(pool.values())


def _merge_candidate(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)

    merged["raw_similarity_score"] = max(
        existing.get("raw_similarity_score") or 0.0,
        incoming.get("raw_similarity_score") or 0.0,
    )
    merged["distance_meters"] = min(
        existing.get("distance_meters") if existing.get("distance_meters") is not None else float("inf"),
        incoming.get("distance_meters") if incoming.get("distance_meters") is not None else float("inf"),
    )
    if merged["distance_meters"] == float("inf"):
        merged["distance_meters"] = None

    merged["keyword_overlap"] = max(
        existing.get("keyword_overlap") or 0,
        incoming.get("keyword_overlap") or 0,
    )

    merged["matched_persons"] = list(set(
        (existing.get("matched_persons") or []) +
        (incoming.get("matched_persons") or [])
    ))

    merged["pattern_signals"] = list(set(
        (existing.get("pattern_signals") or []) +
        (incoming.get("pattern_signals") or [])
    ))

    return merged
