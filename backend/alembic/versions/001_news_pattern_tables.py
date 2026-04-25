"""news pattern tables

Revision ID: 001
Revises:
Create Date: 2026-04-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector extension — required for embedding column
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------ #
    # news_fingerprints — one row per ingested video, immutable            #
    # ------------------------------------------------------------------ #
    op.create_table(
        "news_fingerprints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("video_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("location_raw", sa.Text, nullable=True),
        sa.Column("location_name", sa.Text, nullable=True),
        sa.Column("location_lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("location_lng", sa.Numeric(10, 7), nullable=True),
        sa.Column("location_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("persons_involved", postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("severity_score", sa.Numeric(4, 2), nullable=True),
        sa.Column("severity_label", sa.String(20), nullable=True),
        sa.Column("keywords", postgresql.ARRAY(sa.Text), server_default="{}"),
        # Vector column — 768-dim Gemini embedding
        sa.Column("embedding", sa.Text, nullable=True),  # placeholder; raw DDL below
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_epoch", sa.BigInteger, nullable=True),
        sa.Column("thread_id", sa.String(36), nullable=True),
        sa.Column("rag_result", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Replace placeholder TEXT column with proper vector(768)
    op.execute("ALTER TABLE news_fingerprints ALTER COLUMN embedding TYPE vector(768) USING NULL")

    op.create_index("idx_nf_video_id", "news_fingerprints", ["video_id"], unique=True)
    op.create_index("idx_nf_published_epoch", "news_fingerprints", ["published_epoch"])
    op.create_index("idx_nf_thread_id", "news_fingerprints", ["thread_id"])
    op.create_index(
        "idx_nf_event_epoch",
        "news_fingerprints",
        ["event_type", sa.text("published_epoch DESC")],
    )
    # GIN indexes for array containment queries
    op.execute(
        "CREATE INDEX idx_nf_persons ON news_fingerprints USING GIN (persons_involved)"
    )
    op.execute(
        "CREATE INDEX idx_nf_keywords ON news_fingerprints USING GIN (keywords)"
    )
    # IVFFlat index for vector cosine similarity (tuned for ~10k rows)
    op.execute(
        "CREATE INDEX idx_nf_embedding ON news_fingerprints "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)"
    )

    # ------------------------------------------------------------------ #
    # story_threads — mutable aggregate per story arc                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "story_threads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("event_type", sa.String(50), nullable=True),
        sa.Column("location_name", sa.Text, nullable=True),
        sa.Column("location_lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("location_lng", sa.Numeric(10, 7), nullable=True),
        sa.Column("first_story_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_story_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("story_count", sa.Integer, default=1),
        sa.Column("severity_trend", postgresql.ARRAY(sa.Numeric(4, 2)), server_default="{}"),
        sa.Column("is_escalating", sa.Boolean, default=False),
        sa.Column("is_improving", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_st_event_type", "story_threads", ["event_type"])
    op.create_index("idx_st_last_story_at", "story_threads", ["last_story_at"])

    # ------------------------------------------------------------------ #
    # story_thread_links — append-only story ↔ thread join events         #
    # ------------------------------------------------------------------ #
    op.create_table(
        "story_thread_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("video_id", sa.String(64), nullable=False),
        sa.Column("thread_id", sa.String(36), nullable=False),
        sa.Column("pattern_type", sa.String(30), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("context_note", sa.Text, nullable=True),
        sa.Column("is_recurrence", sa.Boolean, default=False),
        sa.Column("is_escalation", sa.Boolean, default=False),
        sa.Column("recurrence_count", sa.Integer, default=0),
        sa.Column("related_story_ids", postgresql.ARRAY(sa.Text), server_default="{}"),
        sa.Column("rag_result", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_stl_video_id", "story_thread_links", ["video_id"])
    op.create_index("idx_stl_thread_id", "story_thread_links", ["thread_id"])

    # ------------------------------------------------------------------ #
    # story_correlations — pairwise similarity edges                       #
    # ------------------------------------------------------------------ #
    op.create_table(
        "story_correlations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("story_a_id", sa.String(64), nullable=False),
        sa.Column("story_b_id", sa.String(64), nullable=False),
        sa.Column("similarity_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("entity_overlap", sa.Numeric(4, 3), nullable=True),
        sa.Column("pattern_type", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_sc_story_a", "story_correlations", ["story_a_id"])
    op.create_index("idx_sc_story_b", "story_correlations", ["story_b_id"])


def downgrade() -> None:
    op.drop_table("story_correlations")
    op.drop_table("story_thread_links")
    op.drop_table("story_threads")
    op.drop_table("news_fingerprints")
    op.execute("DROP EXTENSION IF EXISTS vector")
