import asyncio
from typing import Any, Dict

from app.core.config import settings
from app.services.model_gateway import ModelGateway
from app.services.prompt_registry import get_prompt


class ReporterAgent:
    def __init__(self):
        self.gateway = ModelGateway()

    def run(self, payload: Dict[str, Any]) -> str:
        prompt = get_prompt("reporter")
        user = prompt["user_template"].format(payload=payload)
        text, _meta = asyncio.run(
            self.gateway.generate_text(
                model=settings.model_name_reporter,
                system=prompt["system"],
                user=user,
            )
        )
        return text.strip()
