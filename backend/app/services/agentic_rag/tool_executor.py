"""
ToolExecutor — runs the RouterAgent's plan in parallel using asyncio.gather.
A failing individual tool does NOT block the rest (allSettled semantics).
"""
import asyncio
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.agentic_rag.tools.location_search import search_by_location_and_event
from app.services.agentic_rag.tools.semantic_search import search_by_semantic_similarity
from app.services.agentic_rag.tools.person_search import search_by_person
from app.services.agentic_rag.tools.severity_trend import get_severity_trend
from app.services.agentic_rag.tools.keyword_search import search_by_keyword
from app.services.agentic_rag.tools.thread_search import search_by_thread

logger = logging.getLogger(__name__)

_TOOL_MAP = {
    "search_by_location_and_event": search_by_location_and_event,
    "search_by_semantic_similarity": search_by_semantic_similarity,
    "search_by_person": search_by_person,
    "get_severity_trend": get_severity_trend,
    "search_by_keyword": search_by_keyword,
    "search_by_thread": search_by_thread,
}


def execute_tools(
    db: Session,
    fingerprint: dict,
    tool_calls: list[dict],
) -> tuple[list[dict], dict | None, list[str]]:
    """
    Execute all tool calls from the plan.

    Returns:
        candidate_results  — list of tool result dicts (stories + search_type)
        severity_trend     — GetSeverityTrendResult or None
        failed_tools       — list of tool names that raised
    """
    return asyncio.run(_run_all(db, fingerprint, tool_calls))


async def _run_all(
    db: Session,
    fingerprint: dict,
    tool_calls: list[dict],
) -> tuple[list[dict], dict | None, list[str]]:
    tasks = [_run_one(db, fingerprint, tc) for tc in tool_calls]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[dict] = []
    severity_trend: dict | None = None
    failed: list[str] = []

    for tc, outcome in zip(tool_calls, outcomes):
        tool_name = tc.get("tool", "unknown")
        if isinstance(outcome, Exception):
            logger.warning("Tool %s failed: %s", tool_name, outcome)
            failed.append(tool_name)
            continue
        if tool_name == "get_severity_trend":
            severity_trend = outcome
        else:
            results.append(outcome)

    if failed:
        logger.warning("Failed tools: %s", failed)

    return results, severity_trend, failed


async def _run_one(db: Session, fingerprint: dict, tool_call: dict) -> Any:
    tool_name = tool_call.get("tool")
    fn = _TOOL_MAP.get(tool_name)
    if fn is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    args = dict(tool_call.get("args", {}))
    args["video_id"] = fingerprint["video_id"]

    # Inject embedding for semantic search
    if tool_name == "search_by_semantic_similarity":
        args.setdefault("embedding", fingerprint.get("embedding", []))

    return await asyncio.to_thread(fn, db, **args)
