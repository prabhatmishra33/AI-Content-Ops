from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path


logger = logging.getLogger("app.media_composer")

SHARED_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage"
MIXED_DIR = SHARED_STORAGE_ROOT / "media_mixed"


class MediaComposerService:
    def __init__(self) -> None:
        MIXED_DIR.mkdir(parents=True, exist_ok=True)

    def compose(self, video_path: str, tts_path: str, mode: str = "replace", output_filename: str | None = None) -> dict:
        if mode != "replace":
            raise ValueError("Unsupported mode. Allowed mode: replace")

        src_video = Path(video_path)
        src_audio = Path(tts_path)
        if not src_video.exists() or not src_video.is_file():
            raise FileNotFoundError(f"Video source not found: {video_path}")
        if not src_audio.exists() or not src_audio.is_file():
            raise FileNotFoundError(f"Audio source not found: {tts_path}")

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is not installed or not on PATH")

        out_name = output_filename or f"{src_video.stem}_mixed.mp4"
        output_path = MIXED_DIR / out_name

        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(src_video),
            "-i",
            str(src_audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(
                "media_compose_failed",
                extra={
                    "video_path": video_path,
                    "tts_path": tts_path,
                    "stderr": (result.stderr or "")[:2000],
                    "stdout": (result.stdout or "")[:500],
                },
            )
            raise RuntimeError("ffmpeg media compose failed")

        logger.info("media_compose_ready", extra={"mixed_video_path": str(output_path)})
        return {"mixed_video_path": str(output_path), "mode": mode}
