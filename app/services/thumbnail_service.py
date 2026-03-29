from __future__ import annotations

import logging
from pathlib import Path
import shutil
import subprocess


THUMBNAIL_DIR = Path(__file__).resolve().parents[2] / "storage" / "thumbnails"
logger = logging.getLogger("app.thumbnail")


def generate_thumbnail(video_id: str, video_path: str, second_offset: int = 1) -> str | None:
    src = Path(video_path)
    if not src.exists() or not src.is_file():
        logger.warning(
            "thumbnail_source_missing",
            extra={"video_id": video_id, "video_path": video_path},
        )
        return None

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.error("thumbnail_ffmpeg_not_found", extra={"video_id": video_id})
        return None

    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    out = THUMBNAIL_DIR / f"{video_id}.jpg"

    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(second_offset),
        "-i",
        str(src),
        "-frames:v",
        "1",
        "-vf",
        "scale=640:-1",
        str(out),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(
            "thumbnail_generated",
            extra={
                "video_id": video_id,
                "thumbnail_path": str(out),
                "ffmpeg_returncode": result.returncode,
            },
        )
    except subprocess.CalledProcessError as exc:
        logger.error(
            "thumbnail_ffmpeg_failed",
            extra={
                "video_id": video_id,
                "video_path": video_path,
                "ffmpeg_returncode": exc.returncode,
                "ffmpeg_stderr": (exc.stderr or "")[:2000],
                "ffmpeg_stdout": (exc.stdout or "")[:500],
            },
        )
        return None
    except Exception as exc:
        logger.exception(
            "thumbnail_unexpected_error",
            extra={"video_id": video_id, "video_path": video_path, "error": str(exc)},
        )
        return None
    return str(out)
