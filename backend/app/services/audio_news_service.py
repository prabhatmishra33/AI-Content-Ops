from __future__ import annotations

import datetime
import logging
import subprocess
import uuid
import wave
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.prompt_registry import get_prompt


logger = logging.getLogger("app.audio_news")

AVAILABLE_VOICES = [
    "Aoede",
    "Charon",
    "Fenrir",
    "Kore",
    "Leda",
    "Orus",
    "Puck",
    "Zephyr",
]

AVAILABLE_LOCALES = [
    "en-US",
    "en-IN",
    "en-GB",
    "en-AU",
    "hi-IN",
    "bn-IN",
    "ta-IN",
    "te-IN",
    "mr-IN",
    "gu-IN",
    "kn-IN",
    "ml-IN",
    "es-ES",
    "es-MX",
    "fr-FR",
    "de-DE",
    "it-IT",
    "pt-BR",
    "ja-JP",
    "ko-KR",
    "zh-CN",
    "zh-TW",
    "ar-SA",
    "ru-RU",
    "tr-TR",
    "nl-NL",
    "pl-PL",
    "sv-SE",
    "th-TH",
    "vi-VN",
    "id-ID",
    "ms-MY",
]

# Shared storage root used by the backend services.
SHARED_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage"
AUDIO_NEWS_DIR = SHARED_STORAGE_ROOT / "audio_news"


class AudioNewsService:
    def __init__(self) -> None:
        AUDIO_NEWS_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def list_voices() -> list[str]:
        return list(AVAILABLE_VOICES)

    @staticmethod
    def list_locales() -> list[str]:
        return list(AVAILABLE_LOCALES)

    @staticmethod
    def _get_client() -> genai.Client:
        if settings.google_genai_use_vertexai:
            return genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location or "global",
            )

        api_key = settings.google_api_key or settings.gemini_api_key or settings.model_api_key
        if not api_key:
            raise ValueError("Missing Google API key for audio generation")
        return genai.Client(api_key=api_key)

    @staticmethod
    def _safe_close_client(client: object) -> None:
        close_fn = getattr(client, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception as exc:  # noqa: BLE001
                logger.warning("audio_news_client_close_failed", extra={"error": str(exc)})

    def generate_script(
        self,
        raw_details: str,
        language: str = "English",
        style: str = "professional broadcast reporter",
        script_model: Optional[str] = None,
    ) -> str:
        model = script_model or settings.tts_script_gen_model
        prompt = get_prompt("audio_news_script")
        client = self._get_client()
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt["user_template"].format(raw_details=raw_details, language=language, style=style),
                config=types.GenerateContentConfig(system_instruction=prompt["system"], temperature=0.7),
            )
        finally:
            self._safe_close_client(client)
        script = (response.text or "").strip()
        if not script:
            raise RuntimeError("Script generation returned empty content")
        return script

    def synthesize_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        locale: Optional[str] = None,
        tts_model: Optional[str] = None,
    ) -> bytes:
        model = tts_model or settings.tts_model
        chosen_voice = voice or settings.tts_default_voice
        chosen_locale = locale or settings.tts_default_locale

        config = types.GenerateContentConfig(
            speech_config=types.SpeechConfig(
                language_code=chosen_locale,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=chosen_voice),
                ),
            ),
            temperature=0.9,
        )

        pcm_data = bytearray()
        client = self._get_client()
        try:
            stream = client.models.generate_content_stream(
                model=model,
                contents=text,
                config=config,
            )
            for chunk in stream:
                if not chunk.candidates:
                    continue
                first = chunk.candidates[0]
                if not first.content or not first.content.parts:
                    continue
                part = first.content.parts[0]
                if part.inline_data and part.inline_data.data:
                    pcm_data += part.inline_data.data
        finally:
            self._safe_close_client(client)

        if not pcm_data:
            raise RuntimeError("TTS synthesis returned empty audio")
        return bytes(pcm_data)

    @staticmethod
    def _pcm_to_mp3(pcm: bytes, channels: int = 1, sample_rate: int = 24000, sample_width: int = 2) -> bytes:
        bits = sample_width * 8
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            f"s{bits}le",
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            "-i",
            "pipe:0",
            "-b:a",
            "192k",
            "-f",
            "mp3",
            "pipe:1",
        ]
        proc = subprocess.run(cmd, input=pcm, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg mp3 conversion failed: {(proc.stderr or b'').decode(errors='replace')[:500]}")
        return proc.stdout

    @staticmethod
    def _pcm_to_wav_bytes(pcm: bytes, channels: int = 1, sample_rate: int = 24000, sample_width: int = 2) -> bytes:
        from io import BytesIO

        out = BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)
        return out.getvalue()

    def generate_news_audio(
        self,
        raw_details: str,
        language: str = "English",
        style: str = "professional broadcast reporter",
        voice: Optional[str] = None,
        locale: Optional[str] = None,
        script_model: Optional[str] = None,
        tts_model: Optional[str] = None,
        output_format: str = "mp3",
        forced_filename: Optional[str] = None,
    ) -> dict:
        script = self.generate_script(raw_details=raw_details, language=language, style=style, script_model=script_model)
        pcm = self.synthesize_speech(text=script, voice=voice, locale=locale, tts_model=tts_model)

        output_format = output_format.lower().strip()
        if output_format not in {"mp3", "wav"}:
            raise ValueError("output_format must be 'mp3' or 'wav'")

        if output_format == "mp3":
            data = self._pcm_to_mp3(pcm)
        else:
            data = self._pcm_to_wav_bytes(pcm)

        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if forced_filename:
            filename = forced_filename
        else:
            audio_id = uuid.uuid4().hex[:12]
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"news_{ts}_{audio_id}.{output_format}"

        path = AUDIO_NEWS_DIR / filename
        path.write_bytes(data)

        duration_s = round(len(pcm) / (24000 * 2), 2)
        logger.info(
            "audio_news_generated",
            extra={"audio_path": str(path), "duration_s": duration_s, "output_format": output_format},
        )
        return {
            "filename": filename,
            "filepath": str(path),
            "duration_s": duration_s,
            "voice": voice or settings.tts_default_voice,
            "locale": locale or settings.tts_default_locale,
            "language": language,
            "script": script,
            "format": output_format,
            "created_at": created_at,
        }
