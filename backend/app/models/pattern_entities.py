"""
ORM models for the Agentic RAG pattern-detection subsystem.
These live in a separate Postgres DB (PATTERN_DATABASE_URL), not SQLite.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from app.db.pattern_base import PatternBase


def _uuid() -> str:
    return str(uuid4())


class NewsFingerprint(PatternBase):
    """One row per ingested video. Immutable after creation."""

    __tablename__ = "news_fingerprints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    video_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, unique=True)

    # What happened
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Where
    location_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    location_lng: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    location_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    # Who
    persons_involved: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")

    # Severity
    severity_score: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    severity_label: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Signal
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    # Time
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_epoch: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    # Thread assignment (set by ThreadManager after RAG)
    thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Full AgenticRAGResult stored for Content Creator to consume
    rag_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StoryThread(PatternBase):
    """
    Mutable aggregate: one row per story arc/cluster.
    Updated each time a new story joins the thread.
    """

    __tablename__ = "story_threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    event_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_lat: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    location_lng: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)

    first_story_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_story_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    story_count: Mapped[int] = mapped_column(Integer, default=1)

    # Ordered severity scores — appended each time a story joins
    severity_trend: Mapped[list[float]] = mapped_column(ARRAY(Numeric(4, 2)), server_default="{}")
    is_escalating: Mapped[bool] = mapped_column(Boolean, default=False)
    is_improving: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StoryThreadLink(PatternBase):
    """
    Append-only junction: story ↔ thread with full pattern metadata.
    One row per (story, thread) join event.
    """

    __tablename__ = "story_thread_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    video_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    pattern_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    context_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_recurrence: Mapped[bool] = mapped_column(Boolean, default=False)
    is_escalation: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_count: Mapped[int] = mapped_column(Integer, default=0)

    related_story_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")

    # Full AgenticRAGResult JSON for audit / replay
    rag_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StoryCorrelation(PatternBase):
    """
    Explicit pairwise similarity edges between individual stories.
    Written by the Merger after each pipeline run.
    """

    __tablename__ = "story_correlations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    story_a_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    story_b_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    similarity_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    entity_overlap: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    pattern_type: Mapped[str | None] = mapped_column(String(30), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
