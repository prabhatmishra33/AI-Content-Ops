import asyncio
from typing import Any, Dict

from app.core.config import settings
from app.services.model_gateway import ModelGateway
from app.services.prompt_registry import get_prompt


class ClassificationAgent:
    def __init__(self):
        self.gateway = ModelGateway()

    def run(self, filename: str) -> Dict[str, Any]:
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
