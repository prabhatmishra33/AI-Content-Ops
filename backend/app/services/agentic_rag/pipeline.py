"""
Main Agentic RAG pipeline entry point.
Called by the Celery task after Phase A completes.
"""
import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.correlation_agent import CorrelationAgent
from app.core.config import settings
from app.db.pattern_session import get_pattern_session_factory
from app.services.agentic_rag.fingerprint_store import FingerprintStore
from app.services.agentic_rag.merger import merge_results
from app.services.agentic_rag.router_agent import RouterAgent, build_default_plan
from app.services.agentic_rag.scorer import score_and_rank
from app.services.agentic_rag.synthesiser import Synthesiser, build_degraded_result
from app.services.agentic_rag.thread_manager import assign_thread
from app.services.agentic_rag.tool_executor import execute_tools

logger = logging.getLogger(__name__)


def run_correlation_pipeline(
    video_id: str,
    video_path: str,
    ai_context: dict | None = None,
) -> dict | None:
    """
    Full pipeline:
      CorrelationAgent → fingerprint + embed
      RouterAgent      → tool plan
      ToolExecutor     → candidate stories
      Merger + Scorer  → ranked results
      Synthesiser      → pattern classification
      ThreadManager    → DB writes
      Returns AgenticRAGResult or None if pattern DB unavailable.
    """
    factory = get_pattern_session_factory()
    if factory is None:
        logger.warning("Pattern DB unavailable — skipping correlation pipeline for %s", video_id)
        return None

    t_total_start = time.monotonic()

    with factory() as pattern_db:
        # ── Phase A: extract fingerprint ─────────────────────────────── #
        try:
            agent = CorrelationAgent()
            fingerprint = agent.run(video_path, ai_context=ai_context)
            fingerprint["video_id"] = video_id
        except Exception as exc:
            logger.error("CorrelationAgent failed for %s: %s", video_id, exc)
            return None

        record = FingerprintStore.upsert(pattern_db, video_id, fingerprint)

        # ── Phase B: plan tool calls ──────────────────────────────────── #
        t_router_start = time.monotonic()
        router_fallback = False
        try:
            router = RouterAgent()
            plan = router.plan(fingerprint)
        except Exception as exc:
            logger.warning("RouterAgent failed (%s) — using default plan", exc)
            plan = build_default_plan(fingerprint)
            router_fallback = True
        t_router_ms = int((time.monotonic() - t_router_start) * 1000)

        # ── Phase C: execute tools in parallel ───────────────────────── #
        t_tools_start = time.monotonic()
        tool_results, severity_trend, failed_tools = execute_tools(
            pattern_db, fingerprint, plan["tool_calls"]
        )
        t_tools_ms = int((time.monotonic() - t_tools_start) * 1000)

        # ── Phase D: merge + score ────────────────────────────────────── #
        t_rank_start = time.monotonic()
        candidates = merge_results(tool_results)
        if len(candidates) > settings.max_candidates_after_merge:
            candidates = candidates[: settings.max_candidates_after_merge]

        ranked = score_and_rank(candidates, fingerprint, severity_trend)
        ranked["search_types_used"] = list({
            r.get("search_type") for r in tool_results if r.get("search_type")
        })
        t_rank_ms = int((time.monotonic() - t_rank_start) * 1000)

        # ── Phase E: synthesise ───────────────────────────────────────── #
        t_synth_start = time.monotonic()
        try:
            synth = Synthesiser()
            pattern_result = synth.synthesise(ranked, fingerprint)
        except Exception as exc:
            logger.error("Synthesiser failed (%s) — using degraded result", exc)
            pattern_result = build_degraded_result(ranked)
        t_synth_ms = int((time.monotonic() - t_synth_start) * 1000)

        # ── Phase F: thread assignment + DB writes ────────────────────── #
        t_total_ms = int((time.monotonic() - t_total_start) * 1000)

        rag_result = _build_rag_result(
            video_id=video_id,
            fingerprint=fingerprint,
            pattern_result=pattern_result,
            ranked=ranked,
            debug={
                "tools_called": [tc["tool"] for tc in plan["tool_calls"]],
                "failed_tools": failed_tools,
                "router_fallback": router_fallback,
                "router_reasoning": plan.get("reasoning", ""),
                "candidates_found": len(candidates),
                "candidates_kept": len(ranked["top_candidates"]),
                "top_candidate_scores": [
                    {"story_id": c["story_id"], "final_score": c["final_score"]}
                    for c in ranked["top_candidates"][:5]
                ],
                "latency_ms": {
                    "router": t_router_ms,
                    "tools": t_tools_ms,
                    "ranking": t_rank_ms,
                    "synthesiser": t_synth_ms,
                    "total": t_total_ms,
                },
            },
        )

        thread_id = assign_thread(pattern_db, fingerprint, pattern_result, ranked, rag_result)
        rag_result["thread_id"] = thread_id
        FingerprintStore.set_rag_result(pattern_db, video_id, rag_result, thread_id)

        logger.info(
            "Correlation pipeline complete for %s — pattern=%s confidence=%.2f thread=%s latency=%dms",
            video_id,
            rag_result.get("pattern_type"),
            rag_result.get("confidence", 0.0),
            thread_id,
            t_total_ms,
        )
        return rag_result


def _build_rag_result(
    video_id: str,
    fingerprint: dict,
    pattern_result: dict,
    ranked: dict,
    debug: dict,
) -> dict:
    trend = ranked.get("severity_trend")

    # Carry top-candidate details (with dates) so downstream consumers
    # (Content Creator prompt, editor UI) can reference exact past dates.
    related_stories = [
        {
            "story_id":      c.get("story_id"),
            "published_at":  c.get("published_at"),
            "summary":       c.get("summary"),
            "severity_score": c.get("severity_score"),
            "location_name": c.get("location_name"),
            "pattern_signals": c.get("pattern_signals", []),
        }
        for c in ranked.get("top_candidates", [])[:10]
    ]

    return {
        "story_id": video_id,
        "thread_id": None,  # filled after assign_thread
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "pattern_type": pattern_result.get("pattern_type", "new_story"),
        "confidence": pattern_result.get("confidence", 0.0),
        "is_recurrence": pattern_result.get("is_recurrence", False),
        "is_escalation": pattern_result.get("is_escalation", False),
        "is_improvement": pattern_result.get("is_improvement", False),
        "recurrence_count": pattern_result.get("recurrence_count", 0),
        "persons_pattern": pattern_result.get("persons_pattern", False),
        "persons_note": pattern_result.get("persons_note"),
        "context_note": pattern_result.get("context_note", ""),
        "related_story_ids": pattern_result.get("related_story_ids", []),
        "related_stories": related_stories,   # ← includes published_at dates
        "severity_trend": {
            "direction": trend["trend_direction"],
            "slope": trend["trend_slope"],
            "change_pct": trend["severity_change_pct"],
            "data_points": trend["data_points"],
        } if trend and trend.get("trend_direction") != "insufficient_data" else None,
        "debug": debug,
    }
