import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import ProcessingJob, VideoAsset
from app.schemas.common import ApiResponse
from app.schemas.video import JobStatusResponse, UploadCompleteRequest
from app.core.security import get_current_user, require_roles
from app.services import idempotency_service, thumbnail_service, upload_security_service
from app.services.workflow_service import WorkflowService


router = APIRouter(prefix="/videos", tags=["videos"])
workflow = WorkflowService()
SERVICE_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = Path(__file__).resolve().parents[5]
UPLOAD_DIR = PROJECT_ROOT / "storage" / "uploads"
UPLOAD_COMPLETE_IDEMPOTENCY_ENDPOINT = "videos.upload.complete.v2"
UPLOAD_FILE_IDEMPOTENCY_ENDPOINT = "videos.upload.file.v2"


def _resolve_existing_path(file_path: str | None, fallback_dirs: list[Path] | None = None) -> Path | None:
    if not file_path:
        return None
    p = Path(file_path)
    if p.exists() and p.is_file():
        return p

    fallback_dirs = fallback_dirs or []
    basename = p.name
    for d in fallback_dirs:
        candidate = d / basename
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _file_response_or_404(
    file_path: str | None,
    fallback_media_type: str = "application/octet-stream",
    fallback_dirs: list[Path] | None = None,
):
    resolved = _resolve_existing_path(file_path, fallback_dirs=fallback_dirs)
    if not resolved:
        raise HTTPException(status_code=404, detail="File not found")
    media_type = mimetypes.guess_type(str(resolved))[0] or fallback_media_type
    return FileResponse(path=str(resolved), media_type=media_type, filename=resolved.name)


def _upload_fallback_dirs() -> list[Path]:
    return [
        SERVICE_ROOT / "storage" / "uploads",
        PROJECT_ROOT / "storage" / "uploads",
        REPO_ROOT / "storage" / "uploads",
    ]


def _thumbnail_fallback_dirs() -> list[Path]:
    return [
        SERVICE_ROOT / "storage" / "thumbnails",
        PROJECT_ROOT / "storage" / "thumbnails",
        REPO_ROOT / "storage" / "thumbnails",
    ]


@router.post("/upload/complete", response_model=ApiResponse)
def upload_complete(
    payload: UploadCompleteRequest,
    x_idempotency_key: str | None = Header(default=None),
    user=Depends(require_roles("uploader", "admin")),
    db: Session = Depends(get_db),
):
    video_id = f"vid_{uuid4().hex[:12]}"
    uploader_ref = user.username if user.role == "uploader" else payload.uploader_ref or user.username
    thumbnail_uri = (
        thumbnail_service.generate_thumbnail(video_id=video_id, video_path=payload.storage_uri)
        if payload.storage_uri
        else None
    )
    idem_key = payload.idempotency_key or x_idempotency_key
    if idem_key:
        existing = idempotency_service.get_record(db, UPLOAD_COMPLETE_IDEMPOTENCY_ENDPOINT, idem_key)
        if existing:
            return ApiResponse(data=existing.response_json)

    video = VideoAsset(
        video_id=video_id,
        uploader_ref=uploader_ref,
        filename=payload.filename,
        content_type=payload.content_type,
        storage_uri=payload.storage_uri,
        thumbnail_uri=thumbnail_uri,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    job = workflow.create_job(db, video)
    enqueue = workflow.enqueue_phase_a(db, job.job_id)
    response = {
        "video_id": video.video_id,
        "job_id": job.job_id,
        "thumbnail_uri": video.thumbnail_uri,
        "queued": enqueue.get("queued", False),
        "phase_a_task_id": enqueue.get("task_id"),
        "enqueue_error": enqueue.get("error"),
        "deduplicated": enqueue.get("deduplicated", False),
    }
    if idem_key:
        idempotency_service.store_record(db, UPLOAD_COMPLETE_IDEMPOTENCY_ENDPOINT, idem_key, response)
    return ApiResponse(data=response)


@router.post("/upload/file", response_model=ApiResponse)
async def upload_file(
    uploader_ref: str = Form(...),
    idempotency_key: str | None = Form(default=None),
    file: UploadFile = File(...),
    x_idempotency_key: str | None = Header(default=None),
    user=Depends(require_roles("uploader", "admin")),
    db: Session = Depends(get_db),
):
    uploader_ref_resolved = user.username if user.role == "uploader" else (uploader_ref or user.username)
    idem_key = idempotency_key or x_idempotency_key
    if idem_key:
        existing = idempotency_service.get_record(db, UPLOAD_FILE_IDEMPOTENCY_ENDPOINT, idem_key)
        if existing:
            return ApiResponse(data=existing.response_json)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    video_id = f"vid_{uuid4().hex[:12]}"
    safe_name = file.filename.replace("\\", "_").replace("/", "_")
    saved_name = f"{video_id}_{safe_name}"
    target_path = UPLOAD_DIR / saved_name

    content = await file.read()
    try:
        upload_security_service.enforce_file_size(len(content))
        sniffed_mime = upload_security_service.sniff_mime(content, file.filename)
        final_mime = upload_security_service.enforce_allowed_mime(file.content_type, sniffed_mime)
        await upload_security_service.run_malware_scan(content, file.filename)
    except upload_security_service.UploadSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    target_path.write_bytes(content)

    video = VideoAsset(
        video_id=video_id,
        uploader_ref=uploader_ref_resolved,
        filename=file.filename,
        content_type=final_mime,
        storage_uri=str(target_path),
        thumbnail_uri=thumbnail_service.generate_thumbnail(video_id=video_id, video_path=str(target_path)),
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    job = workflow.create_job(db, video)
    enqueue = workflow.enqueue_phase_a(db, job.job_id)
    response = {
        "video_id": video.video_id,
        "job_id": job.job_id,
        "storage_uri": video.storage_uri,
        "thumbnail_uri": video.thumbnail_uri,
        "content_type": video.content_type,
        "queued": enqueue.get("queued", False),
        "phase_a_task_id": enqueue.get("task_id"),
        "enqueue_error": enqueue.get("error"),
        "deduplicated": enqueue.get("deduplicated", False),
    }
    if idem_key:
        idempotency_service.store_record(db, UPLOAD_FILE_IDEMPOTENCY_ENDPOINT, idem_key, response)
    return ApiResponse(
        data=response
    )


@router.get("/history", response_model=ApiResponse)
def list_video_history(
    uploader_ref: str | None = Query(default=None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in {"uploader", "admin", "moderator"}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    target_uploader = uploader_ref
    if user.role != "admin":
        target_uploader = user.username

    stmt = select(VideoAsset)
    if target_uploader:
        stmt = stmt.where(VideoAsset.uploader_ref == target_uploader)
    videos = list(db.scalars(stmt.order_by(VideoAsset.created_at.desc())))

    if not videos:
        return ApiResponse(data=[])

    video_ids = [v.video_id for v in videos]
    jobs = list(db.scalars(select(ProcessingJob).where(ProcessingJob.video_id.in_(video_ids))))
    jobs_by_video = {j.video_id: j for j in jobs}

    return ApiResponse(
        data=[
            {
                "video_id": v.video_id,
                "uploader_ref": v.uploader_ref,
                "filename": v.filename,
                "thumbnail_uri": v.thumbnail_uri,
                "created_at": v.created_at.isoformat(),
                "job_id": jobs_by_video.get(v.video_id).job_id if jobs_by_video.get(v.video_id) else None,
                "state": jobs_by_video.get(v.video_id).state.value if jobs_by_video.get(v.video_id) else "UNKNOWN",
                "priority": jobs_by_video.get(v.video_id).priority.value if jobs_by_video.get(v.video_id) else "UNKNOWN",
            }
            for v in videos
        ]
    )


@router.get("/{video_id}", response_model=ApiResponse)
def get_video(video_id: str, _user=Depends(require_roles("uploader", "moderator", "admin")), db: Session = Depends(get_db)):
    video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return ApiResponse(
        data={
            "video_id": video.video_id,
            "uploader_ref": video.uploader_ref,
            "filename": video.filename,
            "content_type": video.content_type,
            "storage_uri": video.storage_uri,
            "thumbnail_uri": video.thumbnail_uri,
            "created_at": video.created_at.isoformat(),
        }
    )


@router.get("/{video_id}/status", response_model=ApiResponse)
def get_video_status(video_id: str, _user=Depends(require_roles("uploader", "moderator", "admin")), db: Session = Depends(get_db)):
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.video_id == video_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    status = JobStatusResponse(
        job_id=job.job_id,
        video_id=job.video_id,
        state=job.state.value,
        priority=job.priority.value,
        attempts=job.attempts,
        last_error=job.last_error,
        updated_at=job.updated_at,
    )
    return ApiResponse(data=status.model_dump())


@router.get("/{video_id}/thumbnail")
def get_video_thumbnail(video_id: str, _user=Depends(require_roles("uploader", "moderator", "admin")), db: Session = Depends(get_db)):
    video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    resolved = _resolve_existing_path(video.thumbnail_uri, fallback_dirs=_thumbnail_fallback_dirs())
    if not resolved:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    if video.thumbnail_uri != str(resolved):
        video.thumbnail_uri = str(resolved)
        db.commit()
    return _file_response_or_404(str(resolved), fallback_media_type="image/jpeg")


@router.get("/{video_id}/stream")
def stream_video(video_id: str, _user=Depends(require_roles("uploader", "moderator", "admin")), db: Session = Depends(get_db)):
    video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    resolved = _resolve_existing_path(video.storage_uri, fallback_dirs=_upload_fallback_dirs())
    if not resolved:
        raise HTTPException(status_code=404, detail="Video source not found in storage")
    if video.storage_uri != str(resolved):
        video.storage_uri = str(resolved)
        db.commit()
    return _file_response_or_404(str(resolved), fallback_media_type=video.content_type or "video/mp4")
