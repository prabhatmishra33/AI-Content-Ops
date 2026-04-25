from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import AIResult, ProcessingJob, ReportArtifact, ReviewDecision, VideoAsset
from app.models.enums import JobState, PriorityQueue, ReviewDecisionValue, ReviewGate
from app.orchestrator.celery_app import celery_app
from app.services import audit_service, distribution_service, dlq_service, reward_service
from app.services.workflow_service import WorkflowService


workflow = WorkflowService()


def _review_queue_for_priority(priority: PriorityQueue | str) -> str:
    p = priority.value if isinstance(priority, PriorityQueue) else str(priority)
    if p == "P0":
        return settings.queue_review_p0
    if p == "P1":
        return settings.queue_review_p1
    if p == "P2":
        return settings.queue_review_p2
    return settings.queue_hold


@celery_app.task(name="app.orchestrator.tasks.run_phase_a_task")
def run_phase_a_task(job_id: str):
    db = SessionLocal()
    try:
        job = workflow.run_phase_a(db, job_id)
        if job and job.state.value == "AI_PHASE_A_DONE":
            create_gate_1_task.apply_async(kwargs={"job_id": job_id}, queue=_review_queue_for_priority(job.priority))
        return {"job_id": job_id, "state": job.state.value if job else "NOT_FOUND"}
    except Exception as exc:
        dlq_service.add_dlq_event(db, "run_phase_a_task", {"job_id": job_id}, str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.orchestrator.tasks.create_gate_1_task")
def create_gate_1_task(job_id: str):
    db = SessionLocal()
    try:
        task = workflow.create_gate_1_review(db, job_id)
        return {"job_id": job_id, "task_id": task.task_id if task else None}
    except Exception as exc:
        dlq_service.add_dlq_event(db, "create_gate_1_task", {"job_id": job_id}, str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.orchestrator.tasks.handle_gate_1_task")
def handle_gate_1_task(job_id: str):
    db = SessionLocal()
    try:
        job = workflow.handle_gate_1_result(db, job_id)
        if job and job.state.value in {"AI_PHASE_B_DONE", "MEDIA_MIX_READY"}:
            create_gate_2_task.apply_async(kwargs={"job_id": job_id}, queue=_review_queue_for_priority(job.priority))
        return {"job_id": job_id, "state": job.state.value if job else "NOT_FOUND"}
    except Exception as exc:
        dlq_service.add_dlq_event(db, "handle_gate_1_task", {"job_id": job_id}, str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.orchestrator.tasks.create_gate_2_task")
def create_gate_2_task(job_id: str):
    db = SessionLocal()
    try:
        task = workflow.create_gate_2_review(db, job_id)
        return {"job_id": job_id, "task_id": task.task_id if task else None}
    except Exception as exc:
        dlq_service.add_dlq_event(db, "create_gate_2_task", {"job_id": job_id}, str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.orchestrator.tasks.distribute_content_task")
def distribute_content_task(job_id: str):
    db = SessionLocal()
    try:
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))
        if not job:
            return {"job_id": job_id, "state": "NOT_FOUND"}
        video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == job.video_id))
        dist_yt = asyncio.run(distribution_service.distribute_youtube(db, job.video_id, video.storage_uri if video else None))
        dist_secondary = asyncio.run(distribution_service.distribute_secondary(db, job.video_id))
        yt_poll = {}
        if dist_yt.external_id:
            yt_poll = asyncio.run(distribution_service.poll_youtube_status(db, dist_yt.external_id))
        all_success = dist_yt.status in {"SUCCESS", "MOCK_SUCCESS"} and dist_secondary.status in {"SUCCESS", "MOCK_SUCCESS"}

        job.state = JobState.DISTRIBUTED if all_success else JobState.FAILED
        db.commit()
        audit_service.write_audit(
            db,
            "job",
            job.job_id,
            "DISTRIBUTION_COMPLETED",
            None,
            {
                "youtube_status": dist_yt.status,
                "secondary_status": dist_secondary.status,
                "youtube_poll": yt_poll,
                "distribution_success": all_success,
            },
        )
        generate_report_task.apply_async(
            kwargs={
                "job_id": job_id,
                "distribution_success": all_success,
                "youtube_status": dist_yt.status,
                "secondary_status": dist_secondary.status,
            },
            queue=settings.queue_report,
        )
        return {"job_id": job_id, "state": job.state.value, "distribution_success": all_success}
    except Exception as exc:
        dlq_service.add_dlq_event(db, "distribute_content_task", {"job_id": job_id}, str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.orchestrator.tasks.generate_report_task")
def generate_report_task(job_id: str, distribution_success: bool, youtube_status: str, secondary_status: str):
    db = SessionLocal()
    try:
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))
        if not job:
            return {"job_id": job_id, "state": "NOT_FOUND"}
        ai = db.scalar(select(AIResult).where(AIResult.video_id == job.video_id))
        report_text = workflow.reporter.run(
            {
                "video_id": job.video_id,
                "impact_score": ai.impact_score if ai else 0.0,
                "priority": job.priority.value,
                "compliance_status": (ai.compliance or {}).get("status") if ai else "UNKNOWN",
                "distribution": {
                    "youtube": youtube_status,
                    "secondary": secondary_status,
                },
            }
        )
        report = ReportArtifact(video_id=job.video_id, summary=report_text, storage_uri=None)
        db.add(report)
        job.state = JobState.REPORT_READY
        db.commit()
        audit_service.write_audit(
            db,
            "job",
            job.job_id,
            "REPORT_GENERATED",
            None,
            {"distribution_success": distribution_success},
        )
        issue_reward_task.apply_async(
            kwargs={"job_id": job_id, "distribution_success": distribution_success},
            queue=settings.queue_reward,
        )
        return {"job_id": job_id, "state": job.state.value}
    except Exception as exc:
        dlq_service.add_dlq_event(
            db,
            "generate_report_task",
            {"job_id": job_id, "distribution_success": distribution_success},
            str(exc),
        )
        raise
    finally:
        db.close()


@celery_app.task(name="app.orchestrator.tasks.issue_reward_task")
def issue_reward_task(job_id: str, distribution_success: bool):
    db = SessionLocal()
    try:
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))
        if not job:
            return {"job_id": job_id, "state": "NOT_FOUND"}
        if distribution_success:
            reward_service.credit_reward_for_video(db, job.video_id)
            job.state = JobState.COMPLETED
            db.commit()
            audit_service.write_audit(db, "job", job.job_id, "REWARD_CREDITED", None, {"video_id": job.video_id})
        else:
            audit_service.write_audit(
                db,
                "job",
                job.job_id,
                "REWARD_SKIPPED_DISTRIBUTION_FAILED",
                None,
                {"video_id": job.video_id},
            )
        audit_service.write_audit(db, "job", job.job_id, "WORKFLOW_COMPLETED", None, {"video_id": job.video_id})
        return {"job_id": job_id, "state": job.state.value}
    except Exception as exc:
        dlq_service.add_dlq_event(
            db,
            "issue_reward_task",
            {"job_id": job_id, "distribution_success": distribution_success},
            str(exc),
        )
        raise
    finally:
        db.close()


@celery_app.task(name="app.orchestrator.tasks.finalize_job_task")
def finalize_job_task(job_id: str):
    # Kept for compatibility; now delegates to distribution->report->reward pipeline.
    return distribute_content_task(job_id)


@celery_app.task(name="app.orchestrator.tasks.after_review_decision_task")
def after_review_decision_task(job_id: str, gate: str, decision: str):
    db = SessionLocal()
    try:
        if gate == "GATE_1":
            if decision == "APPROVE":
                handle_gate_1_task.apply_async(kwargs={"job_id": job_id}, queue=settings.queue_ai_processing)
                return {"job_id": job_id, "action": "HANDLE_GATE_1_ENQUEUED"}
            return {"job_id": job_id, "action": "NOOP_GATE_1_REJECT"}

        if gate == "GATE_2":
            if decision == "APPROVE":
                distribute_content_task.apply_async(kwargs={"job_id": job_id}, queue=settings.queue_distribution)
                return {"job_id": job_id, "action": "DISTRIBUTION_ENQUEUED"}
            return {"job_id": job_id, "action": "NOOP_GATE_2_REJECT"}

        return {"job_id": job_id, "action": "UNKNOWN_GATE"}
    except Exception as exc:
        dlq_service.add_dlq_event(
            db,
            "after_review_decision_task",
            {"job_id": job_id, "gate": gate, "decision": decision},
            str(exc),
        )
        raise
    finally:
        db.close()
