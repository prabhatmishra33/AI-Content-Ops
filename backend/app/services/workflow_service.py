from uuid import uuid4
import asyncio
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.classification import ClassificationAgent
from app.agents.compliance import ComplianceGovernanceAgent
from app.agents.content import ContentCreationAgent, LocalizationAgent
from app.agents.impact import ImpactScoringAgent
from app.agents.direct_impact import DirectImpactScoringAgent
from app.agents.moderation import ModerationAgent
from app.agents.reporter import ReporterAgent
from app.models.entities import AIResult, AuditEvent, ProcessingJob, ReportArtifact, ReviewDecision, ReviewTask, VideoAsset
from app.models.enums import JobState, PriorityQueue, ReviewDecisionValue, ReviewGate
from app.services import audit_service, distribution_service, policy_service, review_service, reward_service, routing_service
from app.core.config import settings
from app.services.audio_news_service import AudioNewsService
from app.services.media_composer_service import MediaComposerService


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
        self.audio_news = AudioNewsService()
        self.media_composer = MediaComposerService()

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

    @staticmethod
    def _is_transient_error(error_text: str) -> bool:
        e = (error_text or "").lower()
        markers = [
            "429",
            "rate",
            "quota",
            "timeout",
            "timed out",
            "temporarily",
            "unavailable",
            "connection reset",
            "connection aborted",
            "resource exhausted",
            "internal server error",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
        ]
        return any(m in e for m in markers)

    def _with_exponential_retry(self, fn, stage: str, max_attempts: int = 3):
        backoff_seconds = 1.0
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                return fn(), attempt
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= max_attempts or not self._is_transient_error(str(exc)):
                    raise
                time.sleep(backoff_seconds)
                backoff_seconds *= 2
        raise RuntimeError(f"{stage} failed after retries: {last_error}")

    @staticmethod
    def _audio_raw_details(video: VideoAsset, ai: AIResult) -> str:
        tags = (ai.tags or {}).get("tags", [])
        category = (ai.tags or {}).get("primary_category", "")
        summary = (ai.generated_content or {}).get("summary", "")
        localized_summary = (ai.localized_content or {}).get("summary", "")
        compliance_status = (ai.compliance or {}).get("status", "")
        violations = (ai.compliance or {}).get("violations", [])
        return (
            f"Video filename: {video.filename}\n"
            f"Category: {category}\n"
            f"Tags: {', '.join(tags) if isinstance(tags, list) else tags}\n"
            f"Impact score: {ai.impact_score}\n"
            f"Compliance status: {compliance_status}\n"
            f"Compliance violations: {violations}\n"
            f"Generated summary: {summary}\n"
            f"Localized summary: {localized_summary}\n"
        )

    @staticmethod
    def _clear_error_if_recovered(job: ProcessingJob) -> None:
        if job.last_error:
            job.last_error = None

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
        if job.state == JobState.AI_PHASE_A_DONE:
            self._clear_error_if_recovered(job)
        db.commit()
        db.refresh(job)

        # Dispatch Agentic RAG pipeline async — does not block or affect job.state
        if job.state == JobState.AI_PHASE_A_DONE:
            try:
                from app.orchestrator.tasks import process_correlation_task
                process_correlation_task.apply_async(
                    kwargs={"job_id": job.job_id},
                    queue=settings.queue_ai_processing,
                )
            except Exception as _exc:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "Could not enqueue correlation task for %s: %s", job.job_id, _exc
                )

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
            # Enrich content generation with pattern context if available
            rag_context: dict | None = None
            try:
                from app.db.pattern_session import get_pattern_session_factory
                _factory = get_pattern_session_factory()
                if _factory:
                    from app.services.agentic_rag.fingerprint_store import FingerprintStore
                    with _factory() as _pdb:
                        rag_context = FingerprintStore.get_rag_result(_pdb, job.video_id)
            except Exception:
                pass  # RAG enrichment is optional; never block Phase B
            content = self.creator.run(video.filename, ai.tags.get("tags", []), impact_analysis, rag_context=rag_context)
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

        # Audio prep + media composition inside AI Content Prep stage
        try:
            locale = ai.localized_content.get("locale") or settings.tts_default_locale
            language = "Hindi" if str(locale).lower().startswith("hi") else "English"
            raw_details = self._audio_raw_details(video, ai)

            def _gen_audio():
                return self.audio_news.generate_news_audio(
                    raw_details=raw_details,
                    language=language,
                    style="professional broadcast reporter",
                    locale=locale,
                    output_format="mp3",
                    forced_filename=f"{job.video_id}.mp3",
                )

            audio_result, audio_attempts = self._with_exponential_retry(_gen_audio, "audio_generate", max_attempts=3)

            def _compose_media():
                return self.media_composer.compose(
                    video_path=video.storage_uri or "",
                    tts_path=audio_result["filepath"],
                    mode="replace",
                    output_filename=f"{job.video_id}_mixed.mp4",
                )

            mix_result, mix_attempts = self._with_exponential_retry(_compose_media, "media_mix", max_attempts=3)

            generated_content = ai.generated_content or {}
            localized_content = ai.localized_content or {}
            generated_content["audio_news"] = {
                "state": "READY",
                "path": audio_result.get("filepath"),
                "format": audio_result.get("format", "mp3"),
                "voice": audio_result.get("voice"),
                "locale": audio_result.get("locale"),
                "duration_s": audio_result.get("duration_s"),
                "attempts_used": audio_attempts,
            }
            localized_content["media_mix"] = {
                "state": "READY",
                "path": mix_result.get("mixed_video_path"),
                "mode": "replace",
                "attempts_used": mix_attempts,
            }
            ai.generated_content = generated_content
            ai.localized_content = localized_content
            job.state = JobState.MEDIA_MIX_READY
            self._clear_error_if_recovered(job)
            db.commit()
            audit_service.write_audit(
                db,
                "job",
                job.job_id,
                "MEDIA_MIX_READY",
                None,
                {
                    "audio_path": generated_content["audio_news"]["path"],
                    "mixed_video_path": localized_content["media_mix"]["path"],
                },
            )
        except Exception as exc:
            job.priority = PriorityQueue.HOLD
            job.state = JobState.HOLD
            job.attempts += 1
            job.last_error = f"MEDIA_MIX_FAILED: {str(exc)}"
            generated_content = ai.generated_content or {}
            localized_content = ai.localized_content or {}
            generated_content["audio_news"] = {
                "state": "FAILED",
                "error": str(exc),
            }
            localized_content["media_mix"] = {
                "state": "FAILED",
                "error": str(exc),
            }
            ai.generated_content = generated_content
            ai.localized_content = localized_content
            db.commit()
            audit_service.write_audit(
                db,
                "job",
                job.job_id,
                "LLM_UNAVAILABLE_HOLD",
                None,
                {"stage": "audio_mix", "error": str(exc)},
            )
        return job

    def retry_media_mix(self, db: Session, video_id: str):
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.video_id == video_id))
        ai = db.scalar(select(AIResult).where(AIResult.video_id == video_id))
        video = db.scalar(select(VideoAsset).where(VideoAsset.video_id == video_id))
        if not job or not ai or not video:
            return None

        audio_news_meta = (ai.generated_content or {}).get("audio_news", {})
        audio_path = audio_news_meta.get("path")
        needs_audio_regen = not audio_path or not Path(audio_path).exists()

        if needs_audio_regen:
            locale = (ai.localized_content or {}).get("locale") or settings.tts_default_locale
            language = "Hindi" if str(locale).lower().startswith("hi") else "English"
            raw_details = self._audio_raw_details(video, ai)

            audio_result, audio_attempts = self._with_exponential_retry(
                lambda: self.audio_news.generate_news_audio(
                    raw_details=raw_details,
                    language=language,
                    style="professional broadcast reporter",
                    locale=locale,
                    output_format="mp3",
                    forced_filename=f"{video.video_id}.mp3",
                ),
                "audio_generate_retry",
                max_attempts=3,
            )
            generated_content = ai.generated_content or {}
            generated_content["audio_news"] = {
                "state": "READY",
                "path": audio_result.get("filepath"),
                "format": audio_result.get("format", "mp3"),
                "voice": audio_result.get("voice"),
                "locale": audio_result.get("locale"),
                "duration_s": audio_result.get("duration_s"),
                "attempts_used": audio_attempts,
                "regenerated_for_mix": True,
            }
            ai.generated_content = generated_content
            audio_path = audio_result.get("filepath")
            db.commit()
            audit_service.write_audit(
                db,
                "job",
                job.job_id,
                "AUDIO_NEWS_REGENERATED",
                None,
                {"video_id": video_id, "audio_path": audio_path, "reason": "missing_or_deleted_audio"},
            )

        if not audio_path:
            raise ValueError("Audio source could not be prepared for this video")

        result, attempts = self._with_exponential_retry(
            lambda: self.media_composer.compose(
                video_path=video.storage_uri or "",
                tts_path=audio_path,
                mode="replace",
                output_filename=f"{video.video_id}_mixed.mp4",
            ),
            "media_mix_manual",
            max_attempts=3,
        )

        localized_content = ai.localized_content or {}
        localized_content["media_mix"] = {
            "state": "READY",
            "path": result.get("mixed_video_path"),
            "mode": "replace",
            "attempts_used": attempts,
        }
        ai.localized_content = localized_content
        job.state = JobState.MEDIA_MIX_READY
        self._clear_error_if_recovered(job)
        db.commit()
        audit_service.write_audit(
            db,
            "job",
            job.job_id,
            "MEDIA_MIX_READY",
            None,
            {"mixed_video_path": result.get("mixed_video_path"), "manual_retry": True},
        )
        existing_open_gate_2 = db.scalar(
            select(ReviewTask).where(
                ReviewTask.job_id == job.job_id,
                ReviewTask.gate == ReviewGate.GATE_2,
                ReviewTask.status.in_(["PENDING", "IN_PROGRESS"]),
            )
        )
        if not existing_open_gate_2:
            existing_done_gate_2 = db.scalar(
                select(ReviewTask).where(
                    ReviewTask.job_id == job.job_id,
                    ReviewTask.gate == ReviewGate.GATE_2,
                    ReviewTask.status == "DONE",
                )
            )
            if existing_done_gate_2:
                audit_service.write_audit(
                    db,
                    "job",
                    job.job_id,
                    "GATE_2_CREATE_SKIPPED_ALREADY_DONE",
                    None,
                    {"task_id": existing_done_gate_2.task_id, "video_id": video.video_id},
                )
            else:
                self.create_gate_2_review(db, job.job_id)
        else:
            audit_service.write_audit(
                db,
                "job",
                job.job_id,
                "GATE_2_CREATE_SKIPPED_ALREADY_EXISTS",
                None,
                {"task_id": existing_open_gate_2.task_id, "video_id": video.video_id},
            )
        return result

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
