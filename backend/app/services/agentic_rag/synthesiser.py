"""
Synthesiser — LLM call #2.
Takes the ranked candidates and produces the final structured PatternResult
for the editor (context note, pattern classification, thread suggestion).
"""
import json
import logging

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.agentic_rag.date_utils import today_str

logger = logging.getLogger(__name__)

SYNTHESISER_PROMPT = """
You are a senior news editor assistant reviewing a new story for context and patterns.
Today's date: {today}

New story:
  Event type: {event_type}
  Location:   {location_name}
  Severity:   {severity_score}/10 ({severity_label})
  Summary:    "{summary}"
  Persons:    {persons_json}

{trend_section}
Top {n} related past stories found (ordered by relevance):
{candidates_section}

Based on this information, answer:
1. Is this a RECURRENCE — the same type of event happened at this location before?
2. Is there an ESCALATION — is severity getting worse over time?
3. Is there an IMPROVEMENT — is the situation getting better?
4. Are any specific persons involved in multiple events?
5. Does this story belong to an existing thread, or is it a new story arc?

Write a context note (2 sentences, plain language) for the editor.

Respond ONLY with valid JSON:
{{
  "pattern_type": "recurrence" | "escalation" | "improvement" | "related" | "new_story",
  "confidence": 0.0,
  "is_recurrence": false,
  "is_escalation": false,
  "is_improvement": false,
  "recurrence_count": 0,
  "persons_pattern": false,
  "persons_note": null,
  "suggested_thread_action": "join_existing" | "create_new" | "link_related",
  "suggested_thread_id": null,
  "context_note": "",
  "related_story_ids": []
}}
"""


class Synthesiser:
    def __init__(self) -> None:
        api_key = settings.google_api_key or settings.gemini_api_key or settings.model_api_key
        if not api_key:
            raise ValueError("Synthesiser requires GOOGLE_API_KEY")
        self.client = genai.Client(api_key=api_key)

    def synthesise(self, ranked_result: dict, fingerprint: dict) -> dict:
        """
        Returns a PatternResult dict.
        Raises on LLM failure — caller should fall back to build_degraded_result().
        """
        prompt = self._build_prompt(ranked_result, fingerprint)
        response = self.client.models.generate_content(
            model=settings.synthesiser_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=settings.synthesiser_temperature,
                max_output_tokens=settings.synthesiser_max_tokens,
            ),
        )
        return json.loads(response.text)

    def _build_prompt(self, ranked_result: dict, fingerprint: dict) -> str:
        top = ranked_result.get("top_candidates", [])
        trend = ranked_result.get("severity_trend")

        trend_section = ""
        if trend and trend.get("trend_direction") != "insufficient_data":
            pts = trend.get("data_points", [])
            trend_section = (
                f"Severity trend at this location:\n"
                f"  Direction: {trend['trend_direction']}\n"
                f"  Change: {trend['severity_change_pct']}% from first to latest\n"
                f"  Data points: {json.dumps(pts[:5])}\n\n"
            )

        candidates_section = ""
        for i, c in enumerate(top, 1):
            candidates_section += (
                f"[{i}] Story: {c.get('story_id')}\n"
                f"  Date: {c.get('published_at')}  Score: {c.get('final_score')}  "
                f"Signals: {c.get('pattern_signals', [])}\n"
                f"  Summary: \"{c.get('summary', '')}\"\n"
                f"  Severity: {c.get('severity_score')}/10  "
                f"Distance: {c.get('distance_meters', 'N/A')}m\n"
            )

        return SYNTHESISER_PROMPT.format(
            today=today_str(),
            event_type=fingerprint.get("event_type", ""),
            location_name=fingerprint.get("location_name", ""),
            severity_score=fingerprint.get("severity_score", ""),
            severity_label=fingerprint.get("severity_label", ""),
            summary=fingerprint.get("summary", ""),
            persons_json=json.dumps(fingerprint.get("persons_involved", [])),
            trend_section=trend_section,
            n=len(top),
            candidates_section=candidates_section or "No related stories found.",
        )


def build_degraded_result(ranked_result: dict) -> dict:
    """Fallback when Synthesiser LLM call fails."""
    top = ranked_result.get("top_candidates", [])
    recurrence_count = sum(
        1 for c in top if "recurrence" in (c.get("pattern_signals") or [])
    )
    return {
        "pattern_type": "recurrence" if recurrence_count > 1 else "related",
        "confidence": 0.4,
        "is_recurrence": recurrence_count > 1,
        "is_escalation": False,
        "is_improvement": False,
        "recurrence_count": recurrence_count,
        "persons_pattern": False,
        "persons_note": None,
        "suggested_thread_action": "create_new",
        "suggested_thread_id": None,
        "context_note": (
            f"Found {len(top)} related past stories. Manual review recommended."
        ),
        "related_story_ids": [c["story_id"] for c in top[:5]],
    }
