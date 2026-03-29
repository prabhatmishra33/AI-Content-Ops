from uuid import uuid4
import asyncio

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.classification import ClassificationAgent
from app.agents.compliance import ComplianceGovernanceAgent
from app.agents.content import ContentCreationAgent, LocalizationAgent
from app.agents.impact import ImpactScoringAgent
from app.agents.direct_impact import DirectImpactScoringAgent
from app.agents.moderation import ModerationAgent
from app.agents.reporter import ReporterAgent
from app.models.entities import AIResult, AuditEvent, ProcessingJob, ReportArtifact, ReviewDecision, VideoAsset
from app.models.enums import JobState, PriorityQueue, ReviewDecisionValue, ReviewGate
from app.services import audit_service, distribution_service, policy_service, review_service, reward_service, routing_service
from app.core.config import settings


class WorkflowService:
    def __init__(self):
        self.moderation = ModerationAgent()
        self.classifier = ClassificationAgent()
        self.impact = ImpactScoringAgent()
        self.direct_impact = DirectImpactScoringAgent()
        self.compliance = ComplianceGovernanceAgent()
        self.creator = ContentCreationAgent()
        self.localizer = LocalizationAgent()
        self.reporter = ReporterAgent()

    @staticmethod
    def _extract_meta(result: dict) -> dict:
        return result.get("__meta", {}) if isinstance(result, dict) else {}

    @staticmethod
    def _strip_meta(result: dict) -> dict:
        if not isinstance(result, dict):
            return {}
        clean = dict(result)
        clean.pop("__meta", None)
        return clean

    def create_job(self, db: Session, video: VideoAsset) -> ProcessingJob:
        job = ProcessingJob(
            job_id=f"job_{uuid4().hex[:12]}",
            video_id=video.video_id,
            state=JobState.UPLOADED,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        audit_service.write_audit(db, "job", job.job_id, "JOB_CREATED", video.uploader_ref, {"video_id": video.video_id})
        return job

    def enqueue_phase_a(self, db: Session, job_id: str):
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))
        if not job:
            return {"queued": False, "error": "JOB_NOT_FOUND", "task_id": None}

        existing = db.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_type == "job",
                AuditEvent.entity_id == job_id,
                AuditEvent.event_type == "PHASE_A_ENQUEUED",
            )
        )
        if existing:
            existing_task_id = (existing.payload or {}).get("task_id")
            return {"queued": True, "deduplicated": True, "task_id": existing_task_id}

        try:
            from app.orchestrator.tasks import run_phase_a_task

            queued = run_phase_a_task.delay(job_id)
            audit_service.write_audit(
                db,
                "job",
                job_id,
                "PHASE_A_ENQUEUED",
                None,
                {"task_id": queued.id},
            )
            return {"queued": True, "deduplicated": False, "task_id": queued.id}
        except Exception as exc:
            job.state = JobState.HOLD
            job.priority = PriorityQueue.HOLD
            job.attempts += 1
            job.last_error = f"QUEUE_ENQUEUE_FAILED: {str(exc)}"
            db.commit()
            audit_service.write_audit(
                db,
                "job",
                job_id,
                "PHASE_A_ENQUEUE_FAILED",
                None,
                {"error": str(exc)},
            )
            return {"queued": False, "deduplicated": False, "task_id": None, "error": str(exc)}

    def run_phase_a(self, db: Session, job_id: str) -> ProcessingJob | None:
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))
        if not job:
            return None
        video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == job.video_id))
        if not video:
            return None

        try:
            mod = self.moderation.run(video.filename)
            cls = self.classifier.run(video.filename)
            imp = self.direct_impact.run(video.storage_uri)
            cmp = self.compliance.run(mod, cls)
        except Exception as exc:
            job.priority = PriorityQueue.HOLD
            job.state = JobState.HOLD
            job.attempts += 1
            job.last_error = f"LLM_UNAVAILABLE_PHASE_A: {str(exc)}"
            db.commit()
            audit_service.write_audit(
                db,
                "job",
                job.job_id,
                "LLM_UNAVAILABLE_HOLD",
                None,
                {"stage": "phase_a", "error": str(exc)},
            )
            return job

        mod_meta = self._extract_meta(mod)
        cls_meta = self._extract_meta(cls)
        imp_meta = imp.get("components", {})
        cmp_meta = self._extract_meta(cmp)

        ai = db.scalar(select(AIResult).where(AIResult.video_id == video.video_id))
        if not ai:
            ai = AIResult(video_id=video.video_id)
            db.add(ai)
        ai.moderation_flags = self._strip_meta(mod)

        tags_dict = self._strip_meta(cls)
        tags_dict["impact_analysis"] = self._strip_meta(imp)
        ai.tags = tags_dict

        ai.impact_score = float(self._strip_meta(imp).get("impact_score", 0.0))
        ai.compliance = self._strip_meta(cmp)
        job.priority = routing_service.route_priority(db, ai.impact_score)

        # Confidence-based escalation rule:
        # if impact confidence is low, force at least P2 human review.
        impact_confidence = float(self._strip_meta(imp).get("confidence", 0.0))
        if impact_confidence < settings.impact_confidence_min and job.priority.value == "HOLD":
            job.priority = PriorityQueue.P2
        if impact_confidence < settings.impact_confidence_min and job.priority.value in {"P2", "HOLD"}:
            job.state = JobState.AI_PHASE_A_DONE
        else:
            active_policy = policy_service.get_active_policy(db)
            if job.priority.value == "HOLD" and active_policy.hold_auto_create_gate1:
                job.state = JobState.AI_PHASE_A_DONE
            else:
                job.state = JobState.AI_PHASE_A_DONE if job.priority.value != "HOLD" else JobState.HOLD
        db.commit()
        db.refresh(job)

        audit_service.write_audit(
            db,
            "job",
            job.job_id,
            "PHASE_A_COMPLETED",
            None,
            {
                "impact_score": ai.impact_score,
                "impact_confidence": impact_confidence,
                "priority": job.priority.value,
                "compliance": ai.compliance.get("status"),
                "model_meta": {
                    "moderation": mod_meta,
                    "classification": cls_meta,
                    "impact": imp_meta,
                    "compliance": cmp_meta,
                },
            },
        )
        return job

    def create_gate_1_review(self, db: Session, job_id: str):
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))
        if not job:
            return None
        task = review_service.create_review_task(db, job.job_id, job.video_id, ReviewGate.GATE_1, job.priority.value)
        job.state = JobState.IN_REVIEW_GATE_1
        db.commit()
        audit_service.write_audit(db, "review_task", task.task_id, "GATE_1_CREATED", None, {"job_id": job.job_id})
        audit_service.write_audit(
            db,
            "job",
            job.job_id,
            "GATE_1_CREATED",
            None,
            {"task_id": task.task_id, "video_id": job.video_id, "priority": job.priority.value},
        )
        return task

    def escalate_hold_to_gate_1(self, db: Session, job_id: str):
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))
        if not job:
            return None
        if job.state != JobState.HOLD:
            return None
        task = review_service.create_review_task(db, job.job_id, job.video_id, ReviewGate.GATE_1, job.priority.value)
        job.state = JobState.IN_REVIEW_GATE_1
        db.commit()
        audit_service.write_audit(db, "review_task", task.task_id, "HOLD_ESCALATED_TO_GATE_1", None, {"job_id": job.job_id})
        audit_service.write_audit(
            db,
            "job",
            job.job_id,
            "HOLD_ESCALATED_TO_GATE_1",
            None,
            {"task_id": task.task_id, "video_id": job.video_id, "priority": job.priority.value},
        )
        return task

    def handle_gate_1_result(self, db: Session, job_id: str):
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))
        if not job:
            return None
        decision = db.scalar(
            select(ReviewDecision)
            .where(ReviewDecision.video_id == job.video_id, ReviewDecision.gate == ReviewGate.GATE_1)
            .order_by(ReviewDecision.created_at.desc())
        )
        if not decision:
            return job
        if decision.decision == ReviewDecisionValue.REJECT:
            job.state = JobState.REJECTED_GATE_1
            db.commit()
            return job

        ai = db.scalar(select(AIResult).where(AIResult.video_id == job.video_id))
        video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == job.video_id))
        try:
            impact_analysis = ai.tags.get("impact_analysis", {})
            content = self.creator.run(video.filename, ai.tags.get("tags", []), impact_analysis)
            localized = self.localizer.run(content)
        except Exception as exc:
            job.priority = PriorityQueue.HOLD
            job.state = JobState.HOLD
            job.attempts += 1
            job.last_error = f"LLM_UNAVAILABLE_PHASE_B: {str(exc)}"
            db.commit()
            audit_service.write_audit(
                db,
                "job",
                job.job_id,
                "LLM_UNAVAILABLE_HOLD",
                None,
                {"stage": "phase_b", "error": str(exc)},
            )
            return job
        content_meta = self._extract_meta(content)
        localized_meta = self._extract_meta(localized)
        ai.generated_content = self._strip_meta(content)
        ai.localized_content = self._strip_meta(localized)
        job.state = JobState.AI_PHASE_B_DONE
        db.commit()
        audit_service.write_audit(
            db,
            "job",
            job.job_id,
            "PHASE_B_COMPLETED",
            None,
            {
                "locale": ai.localized_content.get("locale"),
                "model_meta": {"content_creation": content_meta, "localization": localized_meta},
            },
        )
        return job

    def create_gate_2_review(self, db: Session, job_id: str):
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))
        if not job:
            return None
        task = review_service.create_review_task(db, job.job_id, job.video_id, ReviewGate.GATE_2, job.priority.value)
        job.state = JobState.IN_REVIEW_GATE_2
        db.commit()
        audit_service.write_audit(db, "review_task", task.task_id, "GATE_2_CREATED", None, {"job_id": job.job_id})
        audit_service.write_audit(
            db,
            "job",
            job.job_id,
            "GATE_2_CREATED",
            None,
            {"task_id": task.task_id, "video_id": job.video_id, "priority": job.priority.value},
        )
        return task

    def finalize_after_gate_2(self, db: Session, job_id: str):
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_id == job_id))
        if not job:
            return None
        decision = db.scalar(
            select(ReviewDecision)
            .where(ReviewDecision.video_id == job.video_id, ReviewDecision.gate == ReviewGate.GATE_2)
            .order_by(ReviewDecision.created_at.desc())
        )
        if not decision:
            return job
        if decision.decision == ReviewDecisionValue.REJECT:
            job.state = JobState.REJECTED_GATE_2
            db.commit()
            return job

        video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == job.video_id))
        dist_yt = asyncio.run(distribution_service.distribute_youtube(db, job.video_id, video.storage_uri if video else None))
        dist_secondary = asyncio.run(distribution_service.distribute_secondary(db, job.video_id))
        all_success = dist_yt.status in {"SUCCESS", "MOCK_SUCCESS"} and dist_secondary.status == "SUCCESS"
        job.state = JobState.DISTRIBUTED if all_success else JobState.FAILED
        db.commit()

        ai = db.scalar(select(AIResult).where(AIResult.video_id == job.video_id))
        try:
            report_text = self.reporter.run(
                {
                    "video_id": job.video_id,
                    "impact_score": ai.impact_score if ai else 0.0,
                    "priority": job.priority.value,
                    "compliance_status": (ai.compliance or {}).get("status") if ai else "UNKNOWN",
                    "distribution": [dist_yt.channel, dist_secondary.channel],
                }
            )
        except Exception as exc:
            job.priority = PriorityQueue.HOLD
            job.state = JobState.HOLD
            job.attempts += 1
            job.last_error = f"LLM_UNAVAILABLE_REPORTER: {str(exc)}"
            db.commit()
            audit_service.write_audit(
                db,
                "job",
                job.job_id,
                "LLM_UNAVAILABLE_HOLD",
                None,
                {"stage": "reporter", "error": str(exc)},
            )
            return job
        report = ReportArtifact(video_id=job.video_id, summary=report_text, storage_uri=None)
        db.add(report)
        job.state = JobState.REPORT_READY
        db.commit()

        if all_success:
            reward_service.credit_reward_for_video(db, job.video_id)
            job.state = JobState.COMPLETED
            db.commit()
        else:
            audit_service.write_audit(
                db,
                "job",
                job.job_id,
                "DISTRIBUTION_PARTIAL_OR_FAILED",
                None,
                {"youtube_status": dist_yt.status, "secondary_status": dist_secondary.status},
            )

        audit_service.write_audit(db, "job", job.job_id, "WORKFLOW_COMPLETED", None, {"video_id": job.video_id})
        return job
