import asyncio
import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.genai_client import get_genai_client
from app.services.model_gateway import ModelGateway
from app.services.prompt_registry import get_prompt

logger = logging.getLogger(__name__)


class ClassificationAgent:
    def __init__(self):
        self.gateway = ModelGateway()

    def run(
        self,
        filename: Optional[str] = None,
        storage_uri: Optional[str] = None,
        gemini_file_cache=None,
    ) -> Dict[str, Any]:
        if storage_uri and gemini_file_cache:
            return self._run_multimodal(storage_uri, gemini_file_cache)
        return self._run_text(filename or storage_uri or "unknown")

    def _run_multimodal(self, storage_uri: str, gemini_file_cache) -> Dict[str, Any]:
        from google.genai import types

        from app.agents.base_multimodal import (
            ENTITY_LOOKUP_TOOL,
            _extract_json,
            run_tool_loop,
        )

        client = get_genai_client(force_vertexai=False)
        model = getattr(settings, "model_name_classification", "gemini-2.5-flash")

        gemini_file = gemini_file_cache.get_or_upload(storage_uri)

        prompt = (
            "You are an enterprise content taxonomy expert. Watch this video carefully. "
            "Classify its content and identify any recognizable real-world entities "
            "(people, places, organizations, events). "
            "Use the lookup_entity_info tool to fetch Wikipedia context for any entities you identify — "
            "this helps produce accurate tags and entity descriptions.\n\n"
            "When done, return ONLY a JSON object with these fields:\n"
            '  "primary_category": string\n'
            '  "tags": array of strings\n'
            '  "named_entities": array of {name: string, type: string, wikipedia_summary: string}\n'
            '  "confidence": float 0.0-1.0\n'
        )

        config = types.GenerateContentConfig(
            tools=[ENTITY_LOOKUP_TOOL],
            temperature=0.2,
            thinking_config=types.ThinkingConfig(thinking_budget=-1),
        )

        contents = [gemini_file, prompt]
        final_text = run_tool_loop(client, model, contents, config)

        data = _extract_json(final_text)
        data["__meta"] = {
            "model": model,
            "direct_vertex": True,
            "prompt_version": "v2_video",
        }
        return data

    def _run_text(self, filename: str) -> Dict[str, Any]:
        prompt = get_prompt("classification")
        user = prompt["user_template"].format(filename=filename)
        data, meta = asyncio.run(
            self.gateway.generate_json(
                model=settings.model_name_classification,
                system=prompt["system"],
                user=user,
            )
        )
        data["__meta"] = {"prompt_version": prompt["version"], **meta}
        return data
