import asyncio
import json
import logging
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.genai_client import get_genai_client
from app.services.model_gateway import ModelGateway
from app.services.prompt_registry import get_prompt

logger = logging.getLogger(__name__)

MODERATION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "flags": {
            "type": "OBJECT",
            "properties": {
                "violence": {"type": "BOOLEAN"},
                "abuse": {"type": "BOOLEAN"},
                "adult": {"type": "BOOLEAN"},
            },
            "required": ["violence", "abuse", "adult"],
        },
        "severity": {"type": "STRING", "enum": ["LOW", "MEDIUM", "HIGH"]},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["flags", "severity", "confidence"],
}


class ModerationAgent:
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

        client = get_genai_client(force_vertexai=False)
        model = getattr(settings, "model_name_moderation", "gemini-2.5-flash")

        gemini_file = gemini_file_cache.get_or_upload(storage_uri)

        from app.agents.base_multimodal import today_context
        prompt = (
            today_context()
            + "You are a video safety moderator. Watch this video carefully. "
            "Analyze the visual and audio content for safety violations. "
            "Identify whether the video contains violence, abuse, or adult/explicit content. "
            "Base your judgment strictly on what is shown and heard in the video.\n\n"
            "Return JSON with: flags (object with violence, abuse, adult as booleans), "
            "severity (LOW/MEDIUM/HIGH), confidence (0.0-1.0)."
        )

        response = client.models.generate_content(
            model=model,
            contents=[gemini_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MODERATION_SCHEMA,
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

    def _run_text(self, filename: str) -> Dict[str, Any]:
        prompt = get_prompt("moderation")
        user = prompt["user_template"].format(filename=filename)
        data, meta = asyncio.run(
            self.gateway.generate_json(
                model=settings.model_name_moderation,
                system=prompt["system"],
                user=user,
            )
        )
        data["__meta"] = {"prompt_version": prompt["version"], **meta}
        return data
