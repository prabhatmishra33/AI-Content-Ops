from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.security import require_roles
from app.schemas.audio_news import AudioNewsGenerateRequest
from app.schemas.common import ApiResponse
from app.services.audio_news_service import AUDIO_NEWS_DIR, AudioNewsService


router = APIRouter(prefix="/audio-news", tags=["audio-news"])
audio_news = AudioNewsService()


@router.get("/options", response_model=ApiResponse)
def get_audio_options(_user=Depends(require_roles("moderator", "admin"))):
    return ApiResponse(
        data={
            "voices": audio_news.list_voices(),
            "locales": audio_news.list_locales(),
            "default_voice": settings.tts_default_voice,
            "default_locale": settings.tts_default_locale,
            "default_language": "English",
            "tts_model": settings.tts_model,
            "script_model": settings.tts_script_gen_model,
        }
    )


@router.post("/generate", response_model=ApiResponse)
def generate_audio(payload: AudioNewsGenerateRequest, _user=Depends(require_roles("moderator", "admin"))):
    result = audio_news.generate_news_audio(
        raw_details=payload.raw_details,
        language=payload.language,
        style=payload.style,
        voice=payload.voice,
        locale=payload.locale,
        script_model=payload.script_model,
        tts_model=payload.tts_model,
    )
    return ApiResponse(data=result)


@router.get("/list", response_model=ApiResponse)
def list_audio_news(_user=Depends(require_roles("moderator", "admin"))):
    AUDIO_NEWS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(AUDIO_NEWS_DIR.glob("*.*"), key=lambda x: x.stat().st_mtime, reverse=True)
    return ApiResponse(
        data=[
            {
                "filename": f.name,
                "filepath": str(f),
                "size_bytes": f.stat().st_size,
            }
            for f in files
            if f.suffix.lower() in {".mp3", ".wav"}
        ]
    )


@router.get("/download", response_class=FileResponse)
def download_audio(
    filename: str = Query(...),
    _user=Depends(require_roles("moderator", "admin")),
):
    safe_name = Path(filename).name
    path = AUDIO_NEWS_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")
    media_type = "audio/mpeg" if path.suffix.lower() == ".mp3" else "audio/wav"
    return FileResponse(path=str(path), filename=path.name, media_type=media_type)
