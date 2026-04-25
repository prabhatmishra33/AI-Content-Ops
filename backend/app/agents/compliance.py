import asyncio
import json
import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.genai_client import get_genai_client
from app.services.model_gateway import ModelGateway
from app.services.prompt_registry import get_prompt

logger = logging.getLogger(__name__)

COMPLIANCE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "status": {"type": "STRING", "enum": ["PASS", "PASS_WITH_WARNINGS", "FAIL"]},
        "violations": {"type": "ARRAY", "items": {"type": "STRING"}},
        "required_disclaimer": {"type": "STRING"},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["status", "violations", "required_disclaimer", "confidence"],
}


class ComplianceGovernanceAgent:
    def __init__(self):
        self.gateway = ModelGateway()

    def run(
        self,
        moderation: Dict[str, Any],
        classification: Dict[str, Any],
        storage_uri: Optional[str] = None,
        gemini_file_cache=None,
    ) -> Dict[str, Any]:
        if storage_uri and gemini_file_cache:
            return self._run_multimodal(moderation, classification, storage_uri, gemini_file_cache)
        if settings.model_provider == "gemini" and settings.agent_search_enabled:
            return self._run_text_with_search(moderation, classification)
        return self._run_text(moderation, classification)

    def _get_regulation_context(self, classification: Dict[str, Any]) -> tuple[str, list]:
        """Pre-search for relevant regulations based on content category."""
        from app.services.search_cache_service import SearchCacheService

        category = classification.get("primary_category", "general content")
        tags = classification.get("tags", [])
        topic = f"{category} {' '.join(tags[:3])}"
        cache = SearchCacheService()
        cached = cache.get(f"compliance:{topic}")
        if cached:
            return cached.get("context", ""), cached.get("sources", [])

        try:
            from google.genai import types
            client = get_genai_client(force_vertexai=False)
            from app.agents.base_multimodal import GOOGLE_SEARCH_TOOL, extract_grounding_metadata
            resp = client.models.generate_content(
                model=getattr(settings, "model_name_compliance", "gemini-2.5-flash"),
                contents=[
                    f"Search for the latest content moderation policies and legal regulations relevant to: {topic}. "
                    "Include: YouTube/Meta platform policies, India IT Act provisions, SEBI rules if financial content, "
                    "GDPR/data privacy if personal data involved, and any recent regulatory updates. "
                    "Return a concise 4-6 sentence summary."
                ],
                config=types.GenerateContentConfig(
                    tools=[GOOGLE_SEARCH_TOOL],
                    temperature=0.1,
                ),
            )
            context = resp.text or ""
            sources = extract_grounding_metadata(resp)
            cache.set(f"compliance:{topic}", {"context": context, "sources": sources})
            return context, sources
        except Exception as exc:
            logger.warning(f"Compliance regulation search failed: {exc}")
            return "", []

    def _run_multimodal(
        self,
        moderation: Dict[str, Any],
        classification: Dict[str, Any],
        storage_uri: str,
        gemini_file_cache,
    ) -> Dict[str, Any]:
        from google.genai import types

        client = get_genai_client(force_vertexai=False)
        model = getattr(settings, "model_name_compliance", "gemini-2.5-flash")

        gemini_file = gemini_file_cache.get_or_upload(storage_uri)

        mod_summary = json.dumps({k: v for k, v in moderation.items() if k != "__meta"})
        cls_summary = json.dumps({k: v for k, v in classification.items() if k != "__meta"})

        # Pre-fetch regulation context via Google Search
        reg_context = ""
        web_sources: list = []
        if settings.agent_search_enabled:
            reg_context, web_sources = self._get_regulation_context(classification)

        reg_prefix = f"CURRENT REGULATION CONTEXT (from Google Search):\n{reg_context}\n\n" if reg_context else ""

        prompt = (
            f"{reg_prefix}"
            "You are a senior legal compliance officer and brand safety expert. "
            "Review the provided video alongside its prior AI moderation and classification results.\n\n"
            f"Moderation analysis: {mod_summary}\n"
            f"Classification analysis: {cls_summary}\n\n"
            "Check for violations across: platform content policies (YouTube/Meta), copyright/IP, "
            "defamation, privacy (GDPR/CCPA/India IT Act), hate speech laws, advertising standards, "
            "and SEBI regulations if financial content is involved. "
            "Consider visual content, spoken words, and on-screen text.\n\n"
            'Return JSON: {"status": "PASS|PASS_WITH_WARNINGS|FAIL", '
            '"violations": [string], "required_disclaimer": string, "confidence": 0.0-1.0}'
        )

        response = client.models.generate_content(
            model=model,
            contents=[gemini_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=COMPLIANCE_SCHEMA,
                temperature=0.1,
            ),
        )

        data = json.loads(response.text)
        data["__meta"] = {
            "model": model,
            "direct_vertex": True,
            "prompt_version": "v3_search",
            "web_sources": web_sources,
        }
        return data

    def _run_text_with_search(
        self,
        moderation: Dict[str, Any],
        classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Gemini text path with regulation search grounding."""
        from google.genai import types
        from app.agents.base_multimodal import extract_grounding_metadata

        client = get_genai_client(force_vertexai=False)
        model = getattr(settings, "model_name_compliance", "gemini-2.5-flash")

        mod_summary = json.dumps({k: v for k, v in moderation.items() if k != "__meta"})
        cls_summary = json.dumps({k: v for k, v in classification.items() if k != "__meta"})

        reg_context, web_sources = self._get_regulation_context(classification)
        reg_prefix = f"CURRENT REGULATION CONTEXT (from Google Search):\n{reg_context}\n\n" if reg_context else ""

        prompt = get_prompt("compliance")
        user = (
            f"{reg_prefix}"
            + prompt["user_template"].format(moderation=mod_summary, classification=cls_summary)
        )

        data, meta = asyncio.run(
            self.gateway.generate_json(
                model=model,
                system=prompt["system"],
                user=user,
            )
        )
        data["__meta"] = {
            "prompt_version": "v2_search",
            "web_sources": web_sources,
            **meta,
        }
        return data

    def _run_text(self, moderation: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
        prompt = get_prompt("compliance")
        user = prompt["user_template"].format(moderation=moderation, classification=classification)
        data, meta = asyncio.run(
            self.gateway.generate_json(
                model=settings.model_name_compliance,
                system=prompt["system"],
                user=user,
            )
        )
        data["__meta"] = {"prompt_version": prompt["version"], **meta}
        return data
