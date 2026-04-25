"""
RouterAgent — LLM call #1.
Reads the NewsFingerprint and decides which retrieval tools to call.
Produces a ToolCallPlan; does not execute tools itself.
"""
import json
import logging
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.agentic_rag.date_utils import today_str

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """
You are a news pattern detection agent. Your job is to decide which search tools
to call to find past stories related to a new incoming story.
Today's date: {today}

New story fingerprint:
{fingerprint_json}

Available tools:
1. search_by_location_and_event  — finds same event type near a lat/lng point
2. search_by_semantic_similarity — finds conceptually similar stories
3. search_by_person              — finds past stories involving named persons
4. get_severity_trend            — retrieves ordered severity scores at a location
5. search_by_keyword             — keyword + event type full-text search
6. search_by_thread              — retrieves all stories in a known thread

Rules:
- Always call search_by_location_and_event if lat/lng is available
- Always call search_by_semantic_similarity
- Call search_by_person only if persons_involved is non-empty
- Call get_severity_trend only if event_type is one of: accident, traffic, flood, fire, infrastructure
- Call search_by_keyword as a fallback if location_lat is null
- Do NOT call search_by_thread unless you have a specific thread_id to look up
- You may call 2-5 tools maximum per plan
- Set conservative time windows: prefer 90 days, extend to 180 for person searches

Respond ONLY with valid JSON in this exact shape:
{{
  "reasoning": "1-2 sentence explanation of why you chose these tools",
  "tool_calls": [
    {{
      "tool": "<tool_name>",
      "args": {{ }},
      "priority": 1
    }}
  ]
}}
"""

VALID_TOOLS = {
    "search_by_location_and_event",
    "search_by_semantic_similarity",
    "search_by_person",
    "get_severity_trend",
    "search_by_keyword",
    "search_by_thread",
}

SEVERITY_TREND_EVENT_TYPES = {"accident", "traffic", "flood", "fire", "infrastructure"}


class RouterAgent:
    def __init__(self) -> None:
        api_key = settings.google_api_key or settings.gemini_api_key or settings.model_api_key
        if not api_key:
            raise ValueError("RouterAgent requires GOOGLE_API_KEY")
        self.client = genai.Client(api_key=api_key)

    def plan(self, fingerprint: dict) -> dict:
        """
        Returns {"reasoning": str, "tool_calls": list[dict]} or raises on failure.
        Caller should catch and fall back to build_default_plan().
        """
        fp_json = json.dumps(
            {k: v for k, v in fingerprint.items() if k != "embedding"},
            default=str,
            indent=2,
        )
        prompt = ROUTER_PROMPT.format(today=today_str(), fingerprint_json=fp_json)

        response = self.client.models.generate_content(
            model=settings.router_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=settings.router_temperature,
                max_output_tokens=settings.router_max_tokens,
            ),
        )
        plan = json.loads(response.text)
        _validate_plan(plan)
        return plan


def build_default_plan(fingerprint: dict) -> dict:
    """Fallback plan used when RouterAgent fails."""
    tool_calls = [
        {
            "tool": "search_by_semantic_similarity",
            "args": {
                "days_back": settings.default_days_back,
                "min_score": settings.semantic_similarity_threshold,
                "limit": 20,
            },
            "priority": 1,
        }
    ]

    if fingerprint.get("location_lat") is not None:
        tool_calls.append({
            "tool": "search_by_location_and_event",
            "args": {
                "event_type": fingerprint.get("event_type", "other"),
                "lat": fingerprint["location_lat"],
                "lng": fingerprint["location_lng"],
                "radius_meters": settings.default_location_radius_meters,
                "days_back": settings.default_days_back,
                "limit": 15,
            },
            "priority": 1,
        })
    else:
        tool_calls.append({
            "tool": "search_by_keyword",
            "args": {
                "keywords": fingerprint.get("keywords", []),
                "event_type": fingerprint.get("event_type"),
                "days_back": settings.default_days_back,
                "limit": 15,
                "match_threshold": 2,
            },
            "priority": 2,
        })

    return {
        "reasoning": "Default plan (router agent unavailable)",
        "tool_calls": tool_calls,
    }


def _validate_plan(plan: Any) -> None:
    if not isinstance(plan, dict):
        raise ValueError("Plan is not a dict")
    if "tool_calls" not in plan or not isinstance(plan["tool_calls"], list):
        raise ValueError("Plan missing tool_calls list")
    for tc in plan["tool_calls"]:
        if tc.get("tool") not in VALID_TOOLS:
            raise ValueError(f"Unknown tool: {tc.get('tool')}")
