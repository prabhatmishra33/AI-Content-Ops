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
        return self._run_text(moderation, classification)

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

        prompt = (
            "You are a governance and brand compliance officer. "
            "Review the provided video alongside its prior AI moderation and classification results.\n\n"
            f"Moderation analysis: {mod_summary}\n"
            f"Classification analysis: {cls_summary}\n\n"
            "Check the actual video content for brand safety and legal compliance violations. "
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
            "prompt_version": "v2_video",
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
