import asyncio
from typing import Any, Dict

from app.core.config import settings
from app.services.model_gateway import ModelGateway
from app.services.prompt_registry import get_prompt


class ContentCreationAgent:
    def __init__(self):
        self.gateway = ModelGateway()

    def run(self, filename: str, tags: list[str], impact_analysis: dict) -> Dict[str, Any]:
        prompt = get_prompt("content_creation")
        user = prompt["user_template"].format(filename=filename, tags=tags, impact_analysis=impact_analysis)
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
