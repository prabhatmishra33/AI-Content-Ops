import time
import json
import logging
from pathlib import Path

from google import genai
from google.genai import types

# from app.core.config import settings

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
        "summary": {"type": "STRING"}
    },
    "required": ["components", "final_score", "final_level", "confidence", "summary"]
}


SCORING_PROMPT = """
Act as a Senior Geopolitical Risk Analyst and Crisis Evaluator. Your job is to provide cold, objective, highly analytical scoring of events based strictly on empirical evidence.

Analyze the provided video thoroughly. Evaluate the systemic impact of the events shown in the video and generate component-wise and final impact scores.

CRITICAL RULES:
1. CHAIN OF THOUGHT: You must extract concrete 'evidence' FIRST, formulate your 'reasoning' SECOND, assign a numerical 'score' (0.0 to 1.0) THIRD, and finally map the 'level'. Do not assign a score before justifying it.
2. NEGATIVE CONSTRAINT: If the video is completely unrelated to news, conflict, disasters, or real-world events (e.g., a gaming tutorial, meme, or cartoon), you MUST score all components as 0.0, set all levels to "low", set confidence to 0.1, and write a brief summary explaining the video is not a real-world event.
3. CONTEXTUAL INFERENCE: If the event is clearly part of a broader catastrophic context (e.g., an international war, a major hurricane, a terrorist attack), you MUST factor that broader systemic impact into components like 'environmental', 'economic', and 'political' rather than scoring them in a vacuum based only on the immediate pixels.
4. MAPPING RULE: You MUST map the numerical 'score' to the correct 'level' category STRICTLY as follows:
   - score >= 0.0 AND < 0.35 -> level: "low"
   - score >= 0.35 AND < 0.65 -> level: "medium"
   - score >= 0.65 AND < 0.85 -> level: "high"
   - score >= 0.85 -> level: "very_high"
5. Do not guess numbers randomly. If evidence is missing for a specific component, score it low and reduce your final confidence.

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
"""


class DirectImpactScoringAgent:
    def __init__(self):
        # self.api_key = settings.google_api_key or settings.gemini_api_key or settings.model_api_key
        self.api_key = "AIzaSyA9ChUPsO7w8EVn70q7WjIsUMRWyGUOVKE"
        if not self.api_key:
            raise ValueError("Google GenAI requires GOOGLE_API_KEY (or gemini/model api key) to be set.")
        self.client = genai.Client(api_key=self.api_key)

    def run(self, video_path: str) -> dict:
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        logger.info(f"Uploading '{path.name}' to Vertex AI for direct impact scoring...")
        uploaded_file = self.client.files.upload(file=str(path))
        
        try:
            logger.info("Waiting for video processing to complete in Gemini Files API...")
            while True:
                file_info = self.client.files.get(name=uploaded_file.name)
                state = file_info.state.name if hasattr(file_info.state, "name") else str(file_info.state)
                if state == "ACTIVE":
                    break
                elif state == "FAILED":
                    raise RuntimeError("Video processing failed in Gemini.")
                time.sleep(3)

            logger.info("Processing complete. Sending prompt to gemini-2.5-flash with Chain-of-Thought...")
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[file_info, SCORING_PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SCORING_SCHEMA,
                    temperature=0.2,
                    thinking_config=types.ThinkingConfig(thinking_budget=-1)
                ),
            )
            
            data = json.loads(response.text)
            
            # Map back to pipeline required schema
            impact_score = float(data.get("final_score", 0.0))
            data["impact_score"] = min(max(impact_score, 0.0), 1.0)
            data["confidence"] = float(data.get("confidence", 0.0))
            
            # Extract basic metric usage string for audit logs
            usage_str = None
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage_str = str(response.usage_metadata)

            data["__meta"] = {
                "model": "gemini-3.1-flash-lite-preview",
                "direct_vertex": True,
                "usage": usage_str
            }
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Vertex AI response as JSON. Raw output: {response.text}")
            raise RuntimeError("Invalid JSON response from Vertex AI") from e
        finally:
            try:
                self.client.files.delete(name=uploaded_file.name)
            except Exception as e:
                logger.warning(f"Failed to cleanup file {uploaded_file.name}: {e}")
# simple main file to teset this
if __name__ == "__main__":
    agent = DirectImpactScoringAgent()
    result = agent.run(r"C:\Users\tanma\projects\storage\uploads\vid_4bc1ca86a136_WhatsApp Video 2026-03-27 at 1.55.45 AM.mp4")
    print(result)