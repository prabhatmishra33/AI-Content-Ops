"""
CorrelationAgent — reads a news video and produces a NewsFingerprint + embedding.

Uses the same Gemini Files API pattern as DirectImpactScoringAgent.
Runs after Phase A completes so it can seed itself from the existing ai_results
(classification tags, impact analysis, summary) alongside raw video understanding.
"""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.agentic_rag.date_utils import today_str

logger = logging.getLogger(__name__)

VALID_EVENT_TYPES = {
    "accident", "traffic", "flood", "fire",
    "protest", "crime", "infrastructure", "weather", "political", "other",
}

FINGERPRINT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "event_type": {
            "type": "STRING",
            "enum": list(VALID_EVENT_TYPES),
        },
        "location_raw": {"type": "STRING"},
        "location_name": {"type": "STRING"},
        "persons_involved": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "severity_score": {"type": "NUMBER"},
        "severity_label": {
            "type": "STRING",
            "enum": ["mild", "moderate", "severe"],
        },
        "keywords": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "summary": {"type": "STRING"},
    },
    "required": [
        "event_type", "location_raw", "location_name",
        "persons_involved", "severity_score", "severity_label",
        "keywords", "summary",
    ],
}

EXTRACTION_PROMPT = """
You are a news correlation analyst. Watch this video carefully and extract structured metadata.
Today's date: {today}

Rules:
- event_type: classify as one of [accident, traffic, flood, fire, protest, crime, infrastructure, weather, political, other]
- location_raw: exact location phrase spoken or shown in the video
- location_name: normalised full name including city, e.g. "Andheri Flyover, Mumbai"
- persons_involved: full names of people explicitly mentioned or shown; empty array if none
- severity_score: float 1.0 (minor) to 10.0 (catastrophic)
- severity_label: "mild" (1-4), "moderate" (4-7), "severe" (7-10)
- keywords: 5-10 relevant nouns/phrases that uniquely identify this story
- summary: 1-2 factual sentences about what happened, where, and who

Additional context from automated analysis:
{ai_context}

Respond ONLY with the JSON object. No markdown, no explanation.
"""


class CorrelationAgent:
    def __init__(self) -> None:
        api_key = settings.google_api_key or settings.gemini_api_key or settings.model_api_key
        if not api_key:
            raise ValueError("CorrelationAgent requires GOOGLE_API_KEY")
        self.client = genai.Client(api_key=api_key)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def run(self, video_path: str, ai_context: dict | None = None) -> dict[str, Any]:
        """
        Analyse a video and return a NewsFingerprint dict ready for FingerprintStore.

        Args:
            video_path: absolute path to the uploaded video file
            ai_context: dict of existing ai_results fields (tags, impact_analysis, etc.)

        Returns dict with all NewsFingerprint fields plus 'embedding' (list[float]).
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        context_str = self._format_ai_context(ai_context or {})

        logger.info("CorrelationAgent: uploading %s to Gemini Files API", path.name)
        uploaded_file = self.client.files.upload(file=str(path))

        try:
            uploaded_file = self._wait_for_active(uploaded_file)

            fingerprint = self._extract_fingerprint(uploaded_file, context_str)
            fingerprint["embedding"] = self._embed(fingerprint)
            fingerprint["published_at"] = datetime.now(timezone.utc).isoformat()
            fingerprint["published_epoch"] = int(datetime.now(timezone.utc).timestamp())

            logger.info(
                "CorrelationAgent: fingerprint extracted — event=%s location=%s",
                fingerprint.get("event_type"),
                fingerprint.get("location_name"),
            )
            return fingerprint

        finally:
            try:
                self.client.files.delete(name=uploaded_file.name)
            except Exception as exc:
                logger.warning("CorrelationAgent: failed to delete uploaded file: %s", exc)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _wait_for_active(self, uploaded_file) -> Any:
        while True:
            file_info = self.client.files.get(name=uploaded_file.name)
            state = file_info.state.name if hasattr(file_info.state, "name") else str(file_info.state)
            if state == "ACTIVE":
                return file_info
            if state == "FAILED":
                raise RuntimeError("Gemini Files API: video processing failed")
            time.sleep(3)

    def _extract_fingerprint(self, file_info: Any, context_str: str) -> dict:
        prompt = EXTRACTION_PROMPT.format(today=today_str(), ai_context=context_str)
        response = self.client.models.generate_content(
            model=settings.router_model,
            contents=[file_info, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FINGERPRINT_SCHEMA,
                temperature=0.1,
            ),
        )
        data = json.loads(response.text)

        # Sanitise event_type
        if data.get("event_type") not in VALID_EVENT_TYPES:
            data["event_type"] = "other"

        # Clamp severity
        score = float(data.get("severity_score", 5.0))
        data["severity_score"] = max(1.0, min(10.0, score))

        # Normalise persons to lowercase for consistent matching
        data["persons_involved"] = [p.lower().strip() for p in data.get("persons_involved", [])]
        data["keywords"] = [k.lower().strip() for k in data.get("keywords", [])]

        # lat/lng left as null — geocoding is a separate service (out of scope for now)
        data["location_lat"] = None
        data["location_lng"] = None
        data["location_confidence"] = None

        return data

    def _embed(self, fingerprint: dict) -> list[float]:
        """Generate 768-dim embedding from summary + keywords + location."""
        text = " ".join(filter(None, [
            fingerprint.get("summary", ""),
            fingerprint.get("location_name", ""),
            fingerprint.get("event_type", ""),
            " ".join(fingerprint.get("keywords", [])),
        ]))

        try:
            response = self.client.models.embed_content(
                model=settings.gemini_embedding_model,
                contents=text,
            )
            # google-genai SDK: response.embeddings[0].values
            return list(response.embeddings[0].values)
        except Exception as exc:
            logger.warning("CorrelationAgent: embedding failed (%s) — using empty vector", exc)
            return [0.0] * settings.pgvector_dimensions

    @staticmethod
    def _format_ai_context(ai_context: dict) -> str:
        if not ai_context:
            return "No additional context available."
        parts = []
        if ai_context.get("primary_category"):
            parts.append(f"Category: {ai_context['primary_category']}")
        if ai_context.get("tags"):
            parts.append(f"Tags: {', '.join(ai_context['tags'])}")
        if ai_context.get("impact_score") is not None:
            parts.append(f"Impact score: {ai_context['impact_score']:.2f}")
        if ai_context.get("summary"):
            parts.append(f"Generated summary: {ai_context['summary']}")
        return "\n".join(parts) if parts else "No additional context available."
