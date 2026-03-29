from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings


class UploadSecurityError(ValueError):
    pass


def _allowed_mimes() -> set[str]:
    return {m.strip().lower() for m in settings.upload_allowed_mime_types.split(",") if m.strip()}


def enforce_file_size(size_bytes: int) -> None:
    if size_bytes <= 0:
        raise UploadSecurityError("Uploaded file is empty")
    if size_bytes > settings.upload_max_file_size_bytes:
        raise UploadSecurityError(
            f"File too large: {size_bytes} bytes, max allowed is {settings.upload_max_file_size_bytes} bytes"
        )


def sniff_mime(content: bytes, filename: Optional[str]) -> str:
    head = content[:32]
    # MP4 / MOV: ISO BMFF typically contains ftyp near offset 4.
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "video/mp4"
    # AVI: RIFF....AVI
    if len(head) >= 12 and head[0:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "video/x-msvideo"
    # MKV/WebM: EBML header
    if len(head) >= 4 and head[0:4] == b"\x1A\x45\xDF\xA3":
        return "video/x-matroska"
    # Fallback based on extension only if signature unknown.
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".mov":
        return "video/quicktime"
    if suffix == ".avi":
        return "video/x-msvideo"
    if suffix in {".mkv", ".webm"}:
        return "video/x-matroska"
    if suffix == ".mp4":
        return "video/mp4"
    return "application/octet-stream"


def enforce_allowed_mime(declared_mime: Optional[str], sniffed_mime: str) -> str:
    allowed = _allowed_mimes()
    d = (declared_mime or "").lower().strip()
    if d and d not in allowed:
        raise UploadSecurityError(f"Declared MIME type not allowed: {d}")
    if sniffed_mime not in allowed:
        raise UploadSecurityError(f"File signature MIME type not allowed: {sniffed_mime}")
    return sniffed_mime


async def run_malware_scan(content: bytes, filename: str) -> None:
    if not settings.malware_scan_url:
        return
    headers = {"Content-Type": "application/octet-stream", "X-Filename": filename}
    if settings.malware_scan_api_key:
        headers["Authorization"] = f"Bearer {settings.malware_scan_api_key}"
    async with httpx.AsyncClient(timeout=settings.malware_scan_timeout_seconds) as client:
        res = await client.post(settings.malware_scan_url, headers=headers, content=content)
        res.raise_for_status()
        payload = res.json()
    if not bool(payload.get("clean", False)):
        reason = payload.get("reason", "malware scan failed")
        raise UploadSecurityError(f"Malware scan blocked upload: {reason}")
