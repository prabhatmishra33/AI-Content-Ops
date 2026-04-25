import logging
import time
from pathlib import Path
from typing import Any

from google import genai

from google.genai import types

from app.core.config import settings
from app.core.genai_client import get_genai_client

logger = logging.getLogger(__name__)


class GeminiFileCache:
    """Per-request cache that uploads a video to Gemini Files API once and
    shares the active file reference across all agents in a single Phase A run.
    Create a fresh instance per run_phase_a call; call cleanup() in finally."""

    def __init__(self):
        self.client = get_genai_client(force_vertexai=False)
        self._cache: dict[str, Any] = {}

    def get_or_upload(self, storage_uri: str) -> Any:
        if storage_uri in self._cache:
            logger.debug(f"Gemini file cache hit for {storage_uri}")
            return self._cache[storage_uri]

        path = Path(storage_uri)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {storage_uri}")

        logger.info(f"Uploading '{path.name}' to Gemini Files API...")
        try:
            uploaded = self.client.files.upload(
                file=str(path),
                config=types.UploadFileConfig(
                    mime_type="video/mp4",
                    display_name=path.name[:120]  # sanitize/limit length
                )
            )
        except Exception as exc:
            logger.error(f"Gemini upload failed for {path.name}: {exc}")
            # Try to extract more info if it's a google-genai error
            if hasattr(exc, "response") and hasattr(exc.response, "text"):
                logger.error(f"Gemini error response: {exc.response.text}")
            raise
        
        file_info = self._wait_until_active(uploaded)
        self._cache[storage_uri] = file_info
        logger.info(f"Gemini file ready: {file_info.name}")
        return file_info

    def _wait_until_active(self, uploaded_file: Any) -> Any:
        while True:
            file_info = self.client.files.get(name=uploaded_file.name)
            state = file_info.state.name if hasattr(file_info.state, "name") else str(file_info.state)
            if state == "ACTIVE":
                return file_info
            if state == "FAILED":
                raise RuntimeError(f"Gemini file processing failed for {uploaded_file.name}")
            time.sleep(3)

    def cleanup(self) -> None:
        for storage_uri, file_info in list(self._cache.items()):
            try:
                self.client.files.delete(name=file_info.name)
                logger.debug(f"Deleted Gemini file {file_info.name}")
            except Exception as exc:
                logger.warning(f"Failed to delete Gemini file {file_info.name}: {exc}")
        self._cache.clear()
