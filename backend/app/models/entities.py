from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import JobState, PriorityQueue, ReviewDecisionValue, ReviewGate


class VideoAsset(Base):
    __tablename__ = "video_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    uploader_ref: Mapped[str] = mapped_column(String(128), index=True)
    filename: Mapped[str] = mapped_column(String(256))
    content_type: Mapped[str] = mapped_column(String(128), default="video/mp4")
    storage_uri: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    thumbnail_uri: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    video_id: Mapped[str] = mapped_column(String(64), ForeignKey("video_assets.video_id"), index=True)
    state: Mapped[JobState] = mapped_column(Enum(JobState), default=JobState.UPLOADED, index=True)
    priority: Mapped[PriorityQueue] = mapped_column(Enum(PriorityQueue), default=PriorityQueue.HOLD)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AIResult(Base):
    __tablename__ = "ai_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[str] = mapped_column(String(64), ForeignKey("video_assets.video_id"), index=True)
    moderation_flags: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[dict] = mapped_column(JSON, default=dict)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0)
    compliance: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_content: Mapped[dict] = mapped_column(JSON, default=dict)
    localized_content: Mapped[dict] = mapped_column(JSON, default=dict)
    veracity: Mapped[dict] = mapped_column(JSON, default=dict)
    market_sensitivity: Mapped[dict] = mapped_column(JSON, default=dict)
    news_context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("processing_jobs.job_id"), index=True)
    video_id: Mapped[str] = mapped_column(String(64), ForeignKey("video_assets.video_id"), index=True)
    gate: Mapped[ReviewGate] = mapped_column(Enum(ReviewGate), index=True)
    priority: Mapped[PriorityQueue] = mapped_column(Enum(PriorityQueue), index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    reviewer_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("review_tasks.task_id"), index=True)
    video_id: Mapped[str] = mapped_column(String(64), ForeignKey("video_assets.video_id"), index=True)
    gate: Mapped[ReviewGate] = mapped_column(Enum(ReviewGate), index=True)
    decision: Mapped[ReviewDecisionValue] = mapped_column(Enum(ReviewDecisionValue))
    reviewer_ref: Mapped[str] = mapped_column(String(128))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DistributionResult(Base):
    __tablename__ = "distribution_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[str] = mapped_column(String(64), ForeignKey("video_assets.video_id"), index=True)
    channel: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    error_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[str] = mapped_column(String(64), ForeignKey("video_assets.video_id"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    storage_uri: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WalletAccount(Base):
    __tablename__ = "wallet_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uploader_ref: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    balance_points: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RewardTransaction(Base):
    __tablename__ = "reward_transactions"
    __table_args__ = (UniqueConstraint("video_id", "reason", name="uq_video_reward_reason"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uploader_ref: Mapped[str] = mapped_column(String(128), index=True)
    video_id: Mapped[str] = mapped_column(String(64), ForeignKey("video_assets.video_id"), index=True)
    points: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    actor_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ThresholdPolicy(Base):
    __tablename__ = "threshold_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    version: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    threshold_p0: Mapped[float] = mapped_column(Float)
    threshold_p1: Mapped[float] = mapped_column(Float)
    threshold_p2: Mapped[float] = mapped_column(Float)
    impact_confidence_min: Mapped[float] = mapped_column(Float, default=0.60)
    news_trending_escalation_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hold_auto_create_gate1: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"
    __table_args__ = (UniqueConstraint("provider", "account_ref", name="uq_provider_account"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    account_ref: Mapped[str] = mapped_column(String(128), index=True, default="default")
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at_epoch: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeadLetterEvent(Base):
    __tablename__ = "dead_letter_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_name: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="NEW", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    replayed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ReviewEscalation(Base):
    __tablename__ = "review_escalations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("review_tasks.task_id"), index=True)
    from_priority: Mapped[str] = mapped_column(String(16))
    to_priority: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    escalated_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("endpoint", "idempotency_key", name="uq_endpoint_idempotency_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(128), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IntegrationQuotaUsage(Base):
    __tablename__ = "integration_quota_usage"
    __table_args__ = (UniqueConstraint("provider", "day_utc", name="uq_provider_day_quota"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    day_utc: Mapped[str] = mapped_column(String(16), index=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    limit_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
