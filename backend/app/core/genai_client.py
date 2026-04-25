import logging
from google import genai
from app.core.config import settings

logger = logging.getLogger(__name__)

from typing import Optional

def get_genai_client(force_vertexai: Optional[bool] = None) -> genai.Client:
    """Central factory for google-genai Client, respecting Vertex AI settings unless forced."""
    use_vertex = force_vertexai if force_vertexai is not None else settings.google_genai_use_vertexai
    
    if use_vertex:
        logger.debug("Creating Gemini client with Vertex AI backend")
        return genai.Client(
            vertexai=True,
            project=settings.google_cloud_project,
            location=settings.google_cloud_location or "global",
        )
    
    api_key = settings.google_api_key or settings.gemini_api_key or settings.model_api_key
    if not api_key:
        raise ValueError("No Gemini API key found in settings or environment")
    
    logger.debug("Creating Gemini client with standard API backend")
    return genai.Client(api_key=api_key)
