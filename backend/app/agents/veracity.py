import json
import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.genai_client import get_genai_client

logger = logging.getLogger(__name__)

VERACITY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "verified_claims": {"type": "ARRAY", "items": {"type": "STRING"}},
        "disputed_claims": {"type": "ARRAY", "items": {"type": "STRING"}},
        "unverifiable_claims": {"type": "ARRAY", "items": {"type": "STRING"}},
        "veracity_score": {"type": "NUMBER"},
        "summary": {"type": "STRING"},
    },
    "required": ["verified_claims", "disputed_claims", "unverifiable_claims", "veracity_score", "summary"],
}

VERACITY_PROMPT = """You are a senior fact-checker at a major news organization.
Your job is to verify the factual claims made in this content.

Instructions:
1. Extract all factual claims (statistics, events, attributions, statements of fact).
2. Use Google Search to verify each significant claim against current sources.
3. Classify each claim as:
   - verified: confirmed by at least one credible current source
   - disputed: contradicted or questioned by credible sources
   - unverifiable: cannot be confirmed or denied with available information

VERACITY SCORE (0.0 to 1.0):
  1.0 = all claims verified, highly credible
  0.7 = mostly verified with minor gaps
  0.5 = mixed — some claims verified, some disputed
  0.3 = significant disputed or unverified claims
  0.0 = majority of claims disputed or false

Return JSON with: verified_claims[], disputed_claims[], unverifiable_claims[], veracity_score, summary.
"""


class VeracityAgent:
    """Fact-checks claims in video content using Google Search grounding."""

    def run(
        self,
        moderation: Dict[str, Any],
        classification: Dict[str, Any],
        storage_uri: Optional[str] = None,
        gemini_file_cache=None,
    ) -> Dict[str, Any]:
        if not settings.agent_search_enabled:
            return self._mock_result()
        if storage_uri and gemini_file_cache:
            return self._run_multimodal(moderation, classification, storage_uri, gemini_file_cache)
        return self._run_text(moderation, classification)

    def _run_multimodal(
        self,
        moderation: Dict[str, Any],
        classification: Dict[str, Any],
        storage_uri: str,
        gemini_file_cache,
    ) -> Dict[str, Any]:
        from google.genai import types
        from app.agents.base_multimodal import GOOGLE_SEARCH_TOOL, _extract_json, extract_grounding_metadata

        client = get_genai_client(force_vertexai=False)
        model = getattr(settings, "model_name_veracity", "gemini-2.5-flash")

        gemini_file = gemini_file_cache.get_or_upload(storage_uri)

        from app.agents.base_multimodal import today_context
        cls_summary = json.dumps({k: v for k, v in classification.items() if k != "__meta"})
        context = today_context() + f"Content classification: {cls_summary}\n\n"

        # google_search cannot be combined with response_mime_type/response_schema.
        # Parse JSON from text output instead.
        response = client.models.generate_content(
            model=model,
            contents=[gemini_file, context + VERACITY_PROMPT],
            config=types.GenerateContentConfig(
                tools=[GOOGLE_SEARCH_TOOL],
                temperature=0.1,
            ),
        )

        data = _extract_json(response.text)
        data["__meta"] = {
            "model": model,
            "prompt_version": "v1_search",
            "web_sources": extract_grounding_metadata(response),
        }
        return data

    def _run_text(
        self,
        moderation: Dict[str, Any],
        classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        from google.genai import types
        from app.agents.base_multimodal import GOOGLE_SEARCH_TOOL, extract_grounding_metadata

        client = get_genai_client(force_vertexai=False)
        model = getattr(settings, "model_name_veracity", "gemini-2.5-flash")

        tags = classification.get("tags", [])
        category = classification.get("primary_category", "unknown")
        entities = classification.get("named_entities", [])

        from app.agents.base_multimodal import today_context
        user_prompt = (
            today_context()
            + f"Content category: {category}\n"
            + f"Tags: {', '.join(tags[:10]) if tags else 'none'}\n"
            + f"Named entities: {', '.join(e.get('name', '') for e in entities[:5]) if entities else 'none'}\n\n"
            + VERACITY_PROMPT
        )

        # google_search cannot be combined with response_mime_type/response_schema.
        response = client.models.generate_content(
            model=model,
            contents=[user_prompt],
            config=types.GenerateContentConfig(
                tools=[GOOGLE_SEARCH_TOOL],
                temperature=0.1,
            ),
        )

        from app.agents.base_multimodal import _extract_json
        data = _extract_json(response.text)
        data["__meta"] = {
            "model": model,
            "prompt_version": "v1_search_text",
            "web_sources": extract_grounding_metadata(response),
        }
        return data

    def _mock_result(self) -> Dict[str, Any]:
        """Returned when search is disabled (e.g. offline/dev mode)."""
        return {
            "verified_claims": [],
            "disputed_claims": [],
            "unverifiable_claims": [],
            "veracity_score": 0.5,
            "summary": "Fact-checking skipped — search disabled.",
            "__meta": {"prompt_version": "mock"},
        }
