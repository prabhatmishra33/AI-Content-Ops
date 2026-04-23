"""
Audio News Reporter Service
----------------------------
1. generate_script()  – Gemini text model turns raw notes into a broadcast script
2. synthesize_speech() – Gemini TTS model converts the script to audio (PCM)
3. generate_news_audio() – orchestrator that chains both steps and persists as MP3
"""

from __future__ import annotations

import datetime
import os
import uuid
import io
import logging
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.prompt_registry import get_prompt

logger = logging.getLogger(__name__)

# ── Supported voices & locales (kept dynamic — any value the API accepts works) ──

AVAILABLE_VOICES = [
    "Aoede", "Charon", "Fenrir", "Kore", "Leda",
    "Orus", "Puck", "Zephyr",
]

AVAILABLE_LOCALES = [
    "en-US", "en-IN", "en-GB", "en-AU",
    "hi-IN", "bn-IN", "ta-IN", "te-IN", "mr-IN", "gu-IN", "kn-IN", "ml-IN",
    "es-ES", "es-MX", "fr-FR", "de-DE", "it-IT", "pt-BR",
    "ja-JP", "ko-KR", "zh-CN", "zh-TW",
    "ar-SA", "ru-RU", "tr-TR", "nl-NL", "pl-PL", "sv-SE",
    "th-TH", "vi-VN", "id-ID", "ms-MY",
]

STORAGE_DIR = Path(__file__).resolve().parents[2] / "storage" / "audio_news"


class AudioNewsService:
    """End-to-end audio news generation."""

    def __init__(self):
        self._ensure_storage()

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_storage():
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _get_client() -> genai.Client:
        """Return a Gen AI client configured for Vertex AI or API-key mode."""
        if settings.google_genai_use_vertexai:
            project = settings.google_cloud_project or os.getenv("GOOGLE_CLOUD_PROJECT")
            location = settings.google_cloud_location or os.getenv("GOOGLE_CLOUD_REGION", "global")
            return genai.Client(vertexai=True, project=project, location=location)
        api_key = settings.google_api_key or settings.gemini_api_key or settings.model_api_key
        if not api_key:
            raise ValueError("No Google API key configured for Gen AI client")
        return genai.Client(api_key=api_key)

    @staticmethod
    def _pcm_to_mp3(pcm: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2) -> bytes:
        """Convert raw PCM bytes to MP3 using ffmpeg (subprocess).

        Pipes raw PCM into ffmpeg's stdin and reads MP3 from stdout.
        No temp files, no Python audio libraries needed.
        """
        import subprocess

        bits = sample_width * 8  # 16
        cmd = [
            "ffmpeg", "-y",
            "-f", f"s{bits}le",       # signed 16-bit little-endian PCM
            "-ar", str(rate),         # sample rate
            "-ac", str(channels),     # mono
            "-i", "pipe:0",           # read from stdin
            "-b:a", "192k",           # bitrate
            "-f", "mp3",              # output format
            "pipe:1",                 # write to stdout
        ]
        proc = subprocess.run(
            cmd,
            input=pcm,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}): {proc.stderr.decode(errors='replace')[:500]}")
        return proc.stdout

    @staticmethod
    def list_voices() -> list[str]:
        return list(AVAILABLE_VOICES)

    @staticmethod
    def list_locales() -> list[str]:
        return list(AVAILABLE_LOCALES)

    # ── Step 1: Script generation ────────────────────────────────────────

    def generate_script(
        self,
        raw_details: str,
        language: str = "English",
        style: str = "professional broadcast reporter",
        script_model: Optional[str] = None,
    ) -> str:
        """
        Turn raw notes / bullet points into a polished news reporter script.

        Parameters
        ----------
        raw_details : str
            The user's raw information — can be bullet points, notes, or unstructured text.
        language : str
            The language the script should be written in (e.g. "English", "Hindi", "Spanish").
        style : str
            Tone/style of the script.
        script_model : str | None
            Override the Gemini model used for script generation.
        """
        model = script_model or settings.tts_script_gen_model
        client = self._get_client()

        prompt_entry = get_prompt("audio_news_script")
        system = prompt_entry["system"]
        user_msg = prompt_entry["user_template"].format(
            raw_details=raw_details,
            language=language,
            style=style,
        )

        logger.info("Generating news script with model=%s language=%s", model, language)

        response = client.models.generate_content(
            model=model,
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.7,
            ),
        )
        script = response.text.strip()
        logger.info("Script generated — %d characters", len(script))
        return script

    # ── Step 2: TTS synthesis ────────────────────────────────────────────

    def synthesize_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        locale: Optional[str] = None,
        tts_model: Optional[str] = None,
    ) -> bytes:
        """
        Convert text to speech using Gemini TTS (streaming).

        Returns raw PCM audio bytes (16-bit, 24 kHz, mono).

        Parameters
        ----------
        text : str
            The text (script) to synthesize.
        voice : str | None
            TTS voice name. Defaults to settings.tts_default_voice.
        locale : str | None
            Language/locale code. Defaults to settings.tts_default_locale.
        tts_model : str | None
            Override the TTS model.
        """
        model = tts_model or settings.tts_model
        voice = voice or settings.tts_default_voice
        locale = locale or settings.tts_default_locale
        client = self._get_client()

        config = types.GenerateContentConfig(
            speech_config=types.SpeechConfig(
                language_code=locale,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice,
                    )
                ),
            ),
            temperature=2.0,
        )

        logger.info("Synthesizing speech: model=%s voice=%s locale=%s", model, voice, locale)

        pcm_data = bytearray()
        chunk_count = 0

        for chunk in client.models.generate_content_stream(
            model=model,
            contents=text,
            config=config,
        ):
            chunk_count += 1
            if (
                chunk.candidates is None
                or not chunk.candidates
                or chunk.candidates[0].content is None
                or not chunk.candidates[0].content.parts
            ):
                continue
            part = chunk.candidates[0].content.parts[0]
            if part.inline_data and part.inline_data.data:
                pcm_data += part.inline_data.data

        logger.info("TTS complete — %d chunks, %d bytes PCM", chunk_count, len(pcm_data))
        return bytes(pcm_data)

    # ── Step 3: Orchestrator ─────────────────────────────────────────────

    def generate_news_audio(
        self,
        raw_details: str,
        language: str = "English",
        style: str = "professional broadcast reporter",
        voice: Optional[str] = None,
        locale: Optional[str] = None,
        script_model: Optional[str] = None,
        tts_model: Optional[str] = None,
    ) -> dict:
        """
        Full pipeline: raw details → script → audio → saved MP3 file.

        Returns a dict with:
            id:         unique identifier for this generation
            script:     the generated script text
            filename:   the MP3 filename on disk
            filepath:   absolute path to the MP3 file
            duration_s: approximate duration in seconds
            voice:      voice used
            locale:     locale used
            created_at: ISO timestamp
        """
        # 1. Generate the script
        script = self.generate_script(
            raw_details=raw_details,
            language=language,
            style=style,
            script_model=script_model,
        )

        # 2. Synthesize speech
        pcm = self.synthesize_speech(
            text=script,
            voice=voice,
            locale=locale,
            tts_model=tts_model,
        )

        # 3. Convert PCM → MP3
        mp3_bytes = self._pcm_to_mp3(pcm)

        # 4. Save to disk
        audio_id = uuid.uuid4().hex[:12]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"news_{timestamp}_{audio_id}.mp3"
        filepath = STORAGE_DIR / filename
        filepath.write_bytes(mp3_bytes)

        # Approximate duration (16-bit mono 24kHz → 2 bytes per sample)
        duration_s = round(len(pcm) / (24000 * 2), 2)

        logger.info("Audio saved: %s (%.1fs)", filepath, duration_s)

        return {
            "id": audio_id,
            "script": script,
            "filename": filename,
            "filepath": str(filepath),
            "duration_s": duration_s,
            "voice": voice or settings.tts_default_voice,
            "locale": locale or settings.tts_default_locale,
            "language": language,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
