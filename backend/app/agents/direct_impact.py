import json
import logging
import time
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.genai_client import get_genai_client

logger = logging.getLogger(__name__)


SCORING_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "components": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "evidence": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    },
                    "reasoning": {"type": "STRING"},
                    "score": {"type": "NUMBER"},
                    "level": {"type": "STRING", "enum": ["low", "medium", "high", "very_high"]}
                },
                "required": ["name", "evidence", "reasoning", "score", "level"]
            }
        },
        "final_score": {"type": "NUMBER"},
        "final_level": {"type": "STRING", "enum": ["low", "medium", "high", "very_high"]},
        "confidence": {"type": "NUMBER"},
        "summary": {"type": "STRING"},
        "market_sensitivity": {
            "type": "OBJECT",
            "properties": {
                "is_market_sensitive": {"type": "BOOLEAN"},
                "affected_entities": {"type": "ARRAY", "items": {"type": "STRING"}},
                "sebi_risk": {"type": "STRING", "enum": ["NONE", "LOW", "MEDIUM", "HIGH"]},
                "recommended_action": {"type": "STRING"},
            },
            "required": ["is_market_sensitive", "affected_entities", "sebi_risk", "recommended_action"],
        },
        "news_context": {
            "type": "OBJECT",
            "properties": {
                "is_trending": {"type": "BOOLEAN"},
                "trending_topics": {"type": "ARRAY", "items": {"type": "STRING"}},
                "velocity": {"type": "STRING", "enum": ["NONE", "LOW", "MEDIUM", "HIGH", "BREAKING"]},
            },
            "required": ["is_trending", "trending_topics", "velocity"],
        },
    },
    "required": ["components", "final_score", "final_level", "confidence", "summary", "market_sensitivity", "news_context"]
}

ENTITY_EXTRACTION_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING"},
            "type": {"type": "STRING", "enum": ["person", "place", "organization", "event"]},
        },
        "required": ["name", "type"],
    },
}

SCORING_PROMPT = """
Act as a Senior Geopolitical Risk Analyst and Crisis Evaluator. Your job is to provide cold, objective, highly analytical scoring of events based strictly on empirical evidence.

Analyze the provided video thoroughly. Evaluate the systemic impact of the events shown in the video and generate component-wise and final impact scores.

CRITICAL RULES:
1. CHAIN OF THOUGHT: You must extract concrete 'evidence' FIRST, formulate your 'reasoning' SECOND, assign a numerical 'score' (0.0 to 1.0) THIRD, and finally map the 'level'. Do not assign a score before justifying it.
2. NEGATIVE CONSTRAINT: If the video is completely unrelated to news, conflict, disasters, or real-world events (e.g., a gaming tutorial, meme, or cartoon), you MUST score all components as 0.0, set all levels to "low", set confidence to 0.1, and write a brief summary explaining the video is not a real-world event.
3. CONTEXTUAL INFERENCE: If the event is clearly part of a broader catastrophic context (e.g., an international war, a major hurricane, a terrorist attack), you MUST factor that broader systemic impact into components like 'environmental', 'economic', and 'political' rather than scoring them in a vacuum based only on the immediate pixels.
4. MAPPING RULE: You MUST map any numerical score to the correct 'level' category STRICTLY as follows:
   - score >= 0.0 AND < 0.35 -> level: "low"
   - score >= 0.35 AND < 0.65 -> level: "medium"
   - score >= 0.65 AND < 0.85 -> level: "high"
   - score >= 0.85 -> level: "very_high"
5. Do not guess numbers randomly. If evidence is missing for a specific component, score it low and reduce your final confidence.
6. SUMMARY: Write a 1-2 sentence human-readable summary of the overall event and its assessed impact level.

COMPONENTS TO SCORE (0.0 to 1.0 scale):
- scale: Geographic and population spread (local: 0.1, city: 0.3, state: 0.5, national: 0.75, global: 1.0)
- severity: Consequences and destruction (minimal: 0.1, moderate: 0.4, serious: 0.7, catastrophic: 1.0)
- urgency: Immediacy of the impact (long_term: 0.2, medium_term: 0.5, immediate: 0.9)
- economic: Financial consequences (low: 0.1, sector: 0.4, multi_sector: 0.7, national: 0.9)
- political: Governance/Geopolitical impact (minor: 0.2, policy_change: 0.6, major_shift: 0.85, conflict: 1.0)
- social: Impact on society/behavior (low: 0.2, moderate: 0.5, high: 0.8, transformational: 1.0)
- environmental: Ecological consequences (minimal: 0.1, local: 0.5, large: 0.85, global: 1.0)
- longevity: Duration of impact (temporary: 0.2, short_term: 0.4, long_term: 0.8, permanent: 1.0)
- stakeholder: Affected entities (individual: 0.2, community: 0.5, corporate: 0.7, government: 1.0)
- credibility: Source reliability (assume media-level ~0.7 unless it looks explicitly fake or clearly official/verified)

FINAL SCORE CALCULATION:
Compute 'final_score' as a weighted average of the 10 component scores using the weights below:
  scale       × 0.20
  severity    × 0.20
  urgency     × 0.10
  economic    × 0.10
  political   × 0.10
  social      × 0.10
  environmental × 0.05
  longevity   × 0.05
  stakeholder × 0.05
  credibility × 0.05
  ─────────────────────
  total weight = 1.00

Example: if scale=0.75, severity=0.70, urgency=0.90, economic=0.40, political=0.60, social=0.50, environmental=0.10, longevity=0.40, stakeholder=0.70, credibility=0.70:
  final_score = (0.75×0.20) + (0.70×0.20) + (0.90×0.10) + (0.40×0.10) + (0.60×0.10) + (0.50×0.10) + (0.10×0.05) + (0.40×0.05) + (0.70×0.05) + (0.70×0.05)
  final_score = 0.150 + 0.140 + 0.090 + 0.040 + 0.060 + 0.050 + 0.005 + 0.020 + 0.035 + 0.035 = 0.625

Apply the MAPPING RULE above to derive 'final_level' from 'final_score'.

CONFIDENCE FIELD:
Set 'confidence' (0.0 to 1.0) to reflect how strongly the video evidence supports your scores:
  - 0.9–1.0: Clear, unambiguous footage with verified context
  - 0.7–0.9: Strong visual evidence, context mostly clear
  - 0.5–0.7: Moderate evidence, some inference required
  - 0.3–0.5: Limited evidence, significant inference
  - 0.1–0.3: Weak or ambiguous evidence, low certainty
  - 0.1:     Non-news or irrelevant content (see NEGATIVE CONSTRAINT)

MARKET SENSITIVITY (use the provided current news context to inform this):
Assess whether content involves publicly listed companies or SEBI-regulated information:
- is_market_sensitive: true if content involves listed companies, earnings, M&A, or financial disclosures
- affected_entities: list of company/ticker names that may be affected
- sebi_risk: NONE / LOW / MEDIUM / HIGH — risk level for SEBI-regulated content
- recommended_action: e.g. "Legal review required before publish" or "None"

NEWS VELOCITY (use the provided current news context to inform this):
Based on the current news context provided:
- is_trending: true if the topic is currently breaking or trending in news
- trending_topics: list of specific angles that are trending (empty list if not trending)
- velocity: NONE / LOW / MEDIUM / HIGH / BREAKING — how fast this is moving in the news cycle
"""


class DirectImpactScoringAgent:
    def __init__(self):
        self.client = get_genai_client(force_vertexai=False)

    def run(self, video_path: str, gemini_file_cache=None) -> dict:
        if gemini_file_cache:
            return self._run_with_cache(video_path, gemini_file_cache)
        return self._run_standalone(video_path)

    def _run_with_cache(self, video_path: str, gemini_file_cache) -> dict:
        """Shared-cache path: file upload is managed externally."""
        file_info = gemini_file_cache.get_or_upload(video_path)
        return self._score_with_entity_enrichment(file_info, cleanup_file=False)

    def _run_standalone(self, video_path: str) -> dict:
        """Standalone path for __main__ / direct CLI use — manages its own upload/delete."""
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        logger.info(f"Uploading '{path.name}' to Gemini Files API (standalone mode)...")
        uploaded = self.client.files.upload(
            file=str(path),
            config=types.UploadFileConfig(mime_type="video/mp4")
        )
        file_info = None
        try:
            logger.info("Waiting for video processing...")
            while True:
                file_info = self.client.files.get(name=uploaded.name)
                state = file_info.state.name if hasattr(file_info.state, "name") else str(file_info.state)
                if state == "ACTIVE":
                    break
                if state == "FAILED":
                    raise RuntimeError("Video processing failed in Gemini.")
                time.sleep(3)
            return self._score_with_entity_enrichment(file_info, cleanup_file=False)
        finally:
            try:
                self.client.files.delete(name=uploaded.name)
            except Exception as exc:
                logger.warning(f"Failed to cleanup file {uploaded.name}: {exc}")

    def _score_with_entity_enrichment(self, file_info, cleanup_file: bool = False) -> dict:
        """Three-pass: extract entities → Google Search for current news context → score."""
        from app.agents.base_multimodal import GOOGLE_SEARCH_TOOL, extract_grounding_metadata
        from app.services.search_cache_service import SearchCacheService
        from app.core.config import settings

        model = getattr(settings, "model_name_impact", "gemini-2.5-flash")

        # Pass 1: extract named entities (structured schema — no search needed here)
        entities = []
        try:
            entity_response = self.client.models.generate_content(
                model=model,
                contents=[
                    file_info,
                    (
                        "List all named real-world entities you can identify in this video: "
                        "people, organizations, locations, events. "
                        'Return a JSON array: [{"name": "...", "type": "person|place|organization|event"}]. '
                        "Return an empty array [] if the video contains no real-world entities."
                    ),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ENTITY_EXTRACTION_SCHEMA,
                    temperature=0.1,
                ),
            )
            entities = json.loads(entity_response.text) or []
            logger.info(f"Detected {len(entities)} entities in video")
        except Exception as exc:
            logger.warning(f"Entity extraction pass failed, skipping enrichment: {exc}")

        # Pass 2: Google Search for current news/market context (replaces Wikipedia)
        search_context = ""
        web_sources: list[dict] = []
        if entities and settings.agent_search_enabled:
            entity_names = ", ".join(e["name"] for e in entities[:5])
            cache = SearchCacheService()
            cached = cache.get(entity_names)
            if cached:
                search_context = cached.get("context", "")
                web_sources = cached.get("sources", [])
                logger.info(f"Search cache HIT for entities: {entity_names}")
            else:
                try:
                    from app.agents.base_multimodal import today_context
                    search_response = self.client.models.generate_content(
                        model=model,
                        contents=[
                            today_context()
                            + f"Search for the latest news and context about: {entity_names}. "
                            "Are any involved in breaking news, market events, financial disclosures, or controversy? "
                            "Is this topic currently trending? "
                            "Summarize the most relevant current context in 4-6 sentences."
                        ],
                        config=types.GenerateContentConfig(
                            tools=[GOOGLE_SEARCH_TOOL],
                            temperature=0.1,
                        ),
                    )
                    search_context = search_response.text or ""
                    web_sources = extract_grounding_metadata(search_response)
                    cache.set(entity_names, {"context": search_context, "sources": web_sources})
                    logger.info(f"Search enriched with {len(web_sources)} sources for: {entity_names}")
                except Exception as exc:
                    logger.warning(f"Google Search pass failed, proceeding without: {exc}")

        # Pass 3: full impact scoring with injected search context (structured schema)
        context_prefix = ""
        if search_context:
            context_prefix = (
                "CURRENT NEWS CONTEXT (from Google Search — use this to inform all scoring):\n"
                + search_context
                + "\n\n"
            )

        logger.info("Running impact scoring pass...")
        response = self.client.models.generate_content(
            model=model,
            contents=[file_info, context_prefix + SCORING_PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SCORING_SCHEMA,
                temperature=0.2,
                thinking_config=types.ThinkingConfig(thinking_budget=-1),
            ),
        )

        data = json.loads(response.text)
        data["impact_score"] = min(max(float(data.get("final_score", 0.0)), 0.0), 1.0)
        data["confidence"] = float(data.get("confidence", 0.0))

        usage_str = None
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage_str = str(response.usage_metadata)

        data["__meta"] = {
            "model": model,
            "direct_vertex": True,
            "entities_detected": len(entities),
            "search_sources": len(web_sources),
            "web_sources": web_sources,
            "search_cache_hit": bool(search_context and not web_sources),
            "usage": usage_str,
        }
        return data


if __name__ == "__main__":
    agent = DirectImpactScoringAgent()
    result = agent.run(r"C:\Users\tanma\projects\storage\uploads\vid_4bc1ca86a136_WhatsApp Video 2026-03-27 at 1.55.45 AM.mp4")
    print(result)
