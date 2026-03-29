import asyncio
from typing import Any, Dict

from app.core.config import settings
from app.services.model_gateway import ModelGateway
from app.services.prompt_registry import get_prompt


class ImpactScoringAgent:
    def __init__(self):
        self.gateway = ModelGateway()

    def run(self, moderation: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
        prompt = get_prompt("impact_scoring")
        user = prompt["user_template"].format(moderation=moderation, classification=classification)
        data, meta = asyncio.run(
            self.gateway.generate_json(
                model=settings.model_name_impact,
                system=prompt["system"],
                user=user,
            )
        )
        # normalize and clamp
        score = float(data.get("impact_score", 0.0))
        data["impact_score"] = min(max(score, 0.0), 1.0)
        data["confidence"] = float(data.get("confidence", 0.0))
        data["__meta"] = {"prompt_version": prompt["version"], **meta}
        return data
