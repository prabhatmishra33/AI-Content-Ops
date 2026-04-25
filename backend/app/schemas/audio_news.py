"""Pydantic schemas for Audio News Reporter endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AudioNewsGenerateRequest(BaseModel):
    """Request body for POST /api/v1/audio-news/generate"""

    raw_details: str = Field(
        ...,
        min_length=10,
        description="Raw notes, bullet points, or unstructured text about the news event.",
    )
    language: str = Field(
        default="English",
        description="Language the script should be written in (e.g. English, Hindi, Spanish, French).",
    )
    style: str = Field(
        default="professional broadcast reporter",
        description="Tone / style of the news script.",
    )
    voice: Optional[str] = Field(
        default=None,
        description="TTS voice name (e.g. Kore, Puck, Leda). Null = use server default.",
    )
    locale: Optional[str] = Field(
        default=None,
        description="TTS locale / language code (e.g. en-IN, hi-IN, es-ES). Null = use server default.",
    )
    script_model: Optional[str] = Field(
        default=None,
        description="Override the Gemini model for script generation.",
    )
    tts_model: Optional[str] = Field(
        default=None,
        description="Override the Gemini TTS model.",
    )
    video_duration_s: Optional[float] = Field(
        default=None,
        ge=1.0,
        description="Source video duration in seconds. When provided, the script length is scaled to match the video so the audio podcast matches the video runtime.",
    )


class AudioNewsGenerateResponse(BaseModel):
    """Response body from POST /api/v1/audio-news/generate"""

    id: str
    script: str
    filename: str
    download_url: str
    duration_s: float
    voice: str
    locale: str
    language: str
    created_at: str


class AudioNewsListItem(BaseModel):
    """Single item in the list of generated audio news files."""

    id: str
    filename: str
    download_url: str
    duration_s: float | None = None
    created_at: str | None = None


class AudioNewsOptionsResponse(BaseModel):
    """Available voices and locales for TTS."""

    voices: list[str]
    locales: list[str]
    default_voice: str
    default_locale: str
    default_language: str
    tts_model: str
    script_model: str
