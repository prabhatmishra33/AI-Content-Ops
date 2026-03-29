import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import ProcessingJob, VideoAsset
from app.schemas.common import ApiResponse
from app.schemas.video import JobStatusResponse, UploadCompleteRequest
from app.core.security import require_roles
from app.services import idempotency_service, thumbnail_service, upload_security_service
from app.services.workflow_service import WorkflowService


router = APIRouter(prefix="/videos", tags=["videos"])
workflow = WorkflowService()
UPLOAD_DIR = Path(__file__).resolve().parents[4] / "storage" / "uploads"
UPLOAD_COMPLETE_IDEMPOTENCY_ENDPOINT = "videos.upload.complete.v2"
UPLOAD_FILE_IDEMPOTENCY_ENDPOINT = "videos.upload.file.v2"


def _file_response_or_404(file_path: str | None, fallback_media_type: str = "application/octet-stream"):
    if not file_path:
        raise HTTPException(status_code=404, detail="File not available")
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = mimetypes.guess_type(str(p))[0] or fallback_media_type
    return FileResponse(path=str(p), media_type=media_type, filename=p.name)


@router.post("/upload/complete", response_model=ApiResponse)
def upload_complete(
    payload: UploadCompleteRequest,
    x_idempotency_key: str | None = Header(default=None),
    _user=Depends(require_roles("uploader", "admin")),
    db: Session = Depends(get_db),
):
    video_id = f"vid_{uuid4().hex[:12]}"
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
        uploader_ref=payload.uploader_ref,
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
    _user=Depends(require_roles("uploader", "admin")),
    db: Session = Depends(get_db),
):
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
        uploader_ref=uploader_ref,
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
    return _file_response_or_404(video.thumbnail_uri, fallback_media_type="image/jpeg")


@router.get("/{video_id}/stream")
def stream_video(video_id: str, _user=Depends(require_roles("uploader", "moderator", "admin")), db: Session = Depends(get_db)):
    video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return _file_response_or_404(video.storage_uri, fallback_media_type=video.content_type or "video/mp4")
