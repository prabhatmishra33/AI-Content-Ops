from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from sqlalchemy import text

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.entities import ThresholdPolicy


def migrate() -> None:
    Base.metadata.create_all(bind=engine)
    # Lightweight forward-compatible SQLite migration for existing DB files.
    if settings.database_url.startswith("sqlite:///"):
        with engine.begin() as conn:
            cols = conn.execute(text("PRAGMA table_info(video_assets)")).fetchall()
            col_names = {r[1] for r in cols}
            if "thumbnail_uri" not in col_names:
                conn.execute(text("ALTER TABLE video_assets ADD COLUMN thumbnail_uri VARCHAR(512)"))
                print("Applied migration: video_assets.thumbnail_uri")

            ai_cols = conn.execute(text("PRAGMA table_info(ai_results)")).fetchall()
            ai_col_names = {r[1] for r in ai_cols}
            for col in ("veracity", "market_sensitivity", "news_context"):
                if col not in ai_col_names:
                    conn.execute(text(f"ALTER TABLE ai_results ADD COLUMN {col} JSON"))
                    print(f"Applied migration: ai_results.{col}")

            policy_cols = conn.execute(text("PRAGMA table_info(threshold_policies)")).fetchall()
            policy_col_names = {r[1] for r in policy_cols}
            if "impact_confidence_min" not in policy_col_names:
                conn.execute(
                    text(
                        f"ALTER TABLE threshold_policies ADD COLUMN impact_confidence_min FLOAT NOT NULL DEFAULT {settings.impact_confidence_min}"
                    )
                )
                print("Applied migration: threshold_policies.impact_confidence_min")
            if "news_trending_escalation_enabled" not in policy_col_names:
                conn.execute(
                    text("ALTER TABLE threshold_policies ADD COLUMN news_trending_escalation_enabled BOOLEAN NOT NULL DEFAULT 1")
                )
                print("Applied migration: threshold_policies.news_trending_escalation_enabled")

            # Verify processing_jobs.state can store MEDIA_MIX_READY.
            # Older DBs might have a restrictive CHECK constraint in custom/manual schemas.
            processing_jobs_sql = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='processing_jobs'")
            ).scalar()
            if processing_jobs_sql:
                sql_upper = str(processing_jobs_sql).upper()
                if "CHECK" in sql_upper and "MEDIA_MIX_READY" not in sql_upper:
                    conn.execute(text("ALTER TABLE processing_jobs RENAME TO processing_jobs_old"))
                    conn.execute(
                        text(
                            """
                            CREATE TABLE processing_jobs (
                                id INTEGER NOT NULL PRIMARY KEY,
                                job_id VARCHAR(64) NOT NULL UNIQUE,
                                video_id VARCHAR(64) NOT NULL,
                                state VARCHAR(32) NOT NULL,
                                priority VARCHAR(4) NOT NULL,
                                attempts INTEGER NOT NULL,
                                last_error TEXT,
                                updated_at DATETIME NOT NULL,
                                FOREIGN KEY(video_id) REFERENCES video_assets (video_id)
                            )
                            """
                        )
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO processing_jobs (id, job_id, video_id, state, priority, attempts, last_error, updated_at)
                            SELECT id, job_id, video_id, state, priority, attempts, last_error, updated_at
                            FROM processing_jobs_old
                            """
                        )
                    )
                    conn.execute(text("DROP TABLE processing_jobs_old"))
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_processing_jobs_job_id ON processing_jobs(job_id)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_processing_jobs_video_id ON processing_jobs(video_id)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_processing_jobs_state ON processing_jobs(state)"))
                    print("Applied migration: processing_jobs.state compatibility for MEDIA_MIX_READY")
                else:
                    print("Checked migration: processing_jobs.state already compatible")
    print("Database schema ensured.")


def seed() -> None:
    db = SessionLocal()
    try:
        policy = (
            db.query(ThresholdPolicy)  # type: ignore[attr-defined]
            .filter(ThresholdPolicy.is_active.is_(True))
            .order_by(ThresholdPolicy.created_at.desc())
            .first()
        )
        if not policy:
            db.add(
                ThresholdPolicy(
                    version="v1-default",
                    threshold_p0=settings.threshold_p0,
                    threshold_p1=settings.threshold_p1,
                    threshold_p2=settings.threshold_p2,
                    impact_confidence_min=settings.impact_confidence_min,
                    news_trending_escalation_enabled=True,
                    hold_auto_create_gate1=settings.hold_auto_create_gate1,
                    is_active=True,
                )
            )
            db.commit()
            print("Seeded default active threshold policy.")
        else:
            print("Active policy already exists. Seed skipped.")
    finally:
        db.close()


def reset() -> None:
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path:
        p = Path(db_path)
        if p.exists():
            p.unlink()
            print(f"Deleted DB file: {p}")
    upload_dir = Path(__file__).resolve().parents[1] / "storage" / "uploads"
    if upload_dir.exists():
        for child in upload_dir.iterdir():
            if child.is_file():
                child.unlink()
        print(f"Cleared uploads directory: {upload_dir}")
    thumbnail_dir = Path(__file__).resolve().parents[1] / "storage" / "thumbnails"
    if thumbnail_dir.exists():
        for child in thumbnail_dir.iterdir():
            if child.is_file():
                child.unlink()
        print(f"Cleared thumbnails directory: {thumbnail_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["migrate", "seed", "reset"])
    args = parser.parse_args()

    if args.action == "migrate":
        migrate()
    elif args.action == "seed":
        seed()
    elif args.action == "reset":
        reset()


if __name__ == "__main__":
    main()
