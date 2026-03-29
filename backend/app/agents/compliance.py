import asyncio
from typing import Any, Dict

from app.core.config import settings
from app.services.model_gateway import ModelGateway
from app.services.prompt_registry import get_prompt


class ComplianceGovernanceAgent:
    def __init__(self):
        self.gateway = ModelGateway()

    def run(self, moderation: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
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
