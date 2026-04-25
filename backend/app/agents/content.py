import asyncio
import logging
from typing import Any, Dict

from app.core.config import settings
from app.services.model_gateway import ModelGateway
from app.services.prompt_registry import get_prompt

logger = logging.getLogger(__name__)


class ContentCreationAgent:
    def __init__(self):
        self.gateway = ModelGateway()

    def run(self, filename: str, tags: list[str], impact_analysis: dict) -> Dict[str, Any]:
        trending_context = self._get_trending_context(tags)
        prompt = get_prompt("content_creation")
        user = prompt["user_template"].format(
            filename=filename,
            tags=tags,
            impact_analysis=impact_analysis,
            trending_context=trending_context,
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

    def _get_trending_context(self, tags: list[str]) -> str:
        """Quick Google Search pre-pass to get current trending context for the topic."""
        if not settings.agent_search_enabled or not tags:
            return ""
        try:
            from google.genai import types
            from app.core.genai_client import get_genai_client
            from app.agents.base_multimodal import GOOGLE_SEARCH_TOOL

            topic = ", ".join(tags[:4])
            client = get_genai_client(force_vertexai=False)
            response = client.models.generate_content(
                model=settings.model_name_content,
                contents=[
                    f"Search for the latest trending news and social media discussions about: {topic}. "
                    "What angle, hook, or framing is getting the most engagement right now? "
                    "Return 2-3 sentences of trending context a content creator can use to make content more timely and viral."
                ],
                config=types.GenerateContentConfig(
                    tools=[GOOGLE_SEARCH_TOOL],
                    temperature=0.3,
                ),
            )
            return response.text.strip() if response.text else ""
        except Exception as exc:
            logger.warning("Trending context search failed: %s", exc)
            return ""


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
