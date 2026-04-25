import asyncio
from typing import Any, Dict

from app.core.config import settings
from app.services.model_gateway import ModelGateway
from app.services.prompt_registry import get_prompt
from app.services.agentic_rag.date_utils import today_str


def _format_rag_context(rag_context: dict | None) -> str:
    """
    Builds a date-rich context paragraph for the content creation prompt.
    Example output:
        PATTERN CONTEXT [recurrence | 3 past incidents]:
        - 2026-01-05: "Truck overturns on Andheri Flyover, 2 injured." (severity 4.1)
        - 2026-02-12: "Car hits divider at Andheri Flyover." (severity 5.8)
        - 2026-03-28: "Three vehicles collide near Andheri Flyover." (severity 6.2)
        Severity trend: escalating (+52% change).
        Editor note: "This is the 4th accident at this location in 83 days."
        Use this history to write a title and summary that highlight the recurring danger.
    """
    if not rag_context:
        return ""

    pattern      = rag_context.get("pattern_type", "new_story")
    count        = rag_context.get("recurrence_count", 0)
    context_note = rag_context.get("context_note", "")
    stories      = rag_context.get("related_stories") or []
    trend        = rag_context.get("severity_trend")
    processed_at = rag_context.get("processed_at", "")

    if pattern == "new_story" and not stories:
        return ""

    lines: list[str] = []

    # ── Header ───────────────────────────────────────────────────────── #
    label_map = {
        "recurrence":  f"recurrence | {count} past incident(s)",
        "escalation":  "severity escalating",
        "improvement": "situation improving",
        "related":     "related past stories",
        "new_story":   "new story arc",
    }
    lines.append(f"\nPATTERN CONTEXT [{label_map.get(pattern, pattern)}]:")

    # ── Current story date ───────────────────────────────────────────── #
    if processed_at:
        date_str = processed_at[:10]   # YYYY-MM-DD
        lines.append(f"  Current story date: {date_str}")

    # ── Past incident timeline with dates ────────────────────────────── #
    recurrence_stories = [
        s for s in stories
        if "recurrence" in (s.get("pattern_signals") or [])
    ] or stories[:5]    # fallback to top 5 if no recurrence signals

    if recurrence_stories:
        lines.append("  Past related incidents (chronological):")
        for s in sorted(recurrence_stories, key=lambda x: x.get("published_at") or ""):
            pub   = (s.get("published_at") or "")[:10]
            sev   = s.get("severity_score")
            summ  = (s.get("summary") or "").strip()
            sev_str = f" (severity {sev:.1f}/10)" if sev else ""
            lines.append(f"    - {pub}: \"{summ}\"{sev_str}")

    # ── Severity trend ───────────────────────────────────────────────── #
    if trend and trend.get("direction") not in (None, "insufficient_data", "stable"):
        direction  = trend["direction"]
        change_pct = trend.get("change_pct") or trend.get("severity_change_pct", 0)
        lines.append(f"  Severity trend: {direction} ({change_pct:+.0f}% change over the period).")

    # ── Editor note ──────────────────────────────────────────────────── #
    if context_note:
        lines.append(f"  Editor note: \"{context_note}\"")

    # ── Instruction ──────────────────────────────────────────────────── #
    if pattern == "recurrence":
        lines.append(
            "  Instruction: Reference the incident history and dates above in the title and summary "
            "to convey the recurring nature and urgency of this story."
        )
    elif pattern == "escalation":
        lines.append(
            "  Instruction: Highlight the escalating severity trend with specific dates to show the worsening situation."
        )
    elif pattern == "improvement":
        lines.append(
            "  Instruction: Highlight the improving trend with dates to give readers an encouraging, data-backed narrative."
        )

    return "\n".join(lines) + "\n"


class ContentCreationAgent:
    def __init__(self):
        self.gateway = ModelGateway()

    def run(
        self,
        filename: str,
        tags: list[str],
        impact_analysis: dict,
        rag_context: dict | None = None,
    ) -> Dict[str, Any]:
        prompt = get_prompt("content_creation")
        pattern_context = _format_rag_context(rag_context)
        user = prompt["user_template"].format(
            today=today_str(),
            filename=filename,
            tags=tags,
            impact_analysis=impact_analysis,
            pattern_context=pattern_context,
        )
        data, meta = asyncio.run(
            self.gateway.generate_json(
                model=settings.model_name_content,
                system=prompt["system"],
                user=user,
            )
        )
        data["__meta"] = {"prompt_version": prompt["version"], **meta}
        return data


class LocalizationAgent:
    def __init__(self):
        self.gateway = ModelGateway()

    def run(self, content: Dict[str, Any], locale: str = "hi-IN") -> Dict[str, Any]:
        prompt = get_prompt("localization")
        user = prompt["user_template"].format(content=content, locale=locale)
        data, meta = asyncio.run(
            self.gateway.generate_json(
                model=settings.model_name_localization,
                system=prompt["system"],
                user=user,
            )
        )
        data["__meta"] = {"prompt_version": prompt["version"], **meta}
        return data
