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
    # Lightweight forward-compatible SQLite migration for new nullable columns.
    if settings.database_url.startswith("sqlite:///"):
        with engine.begin() as conn:
            cols = conn.execute(text("PRAGMA table_info(video_assets)")).fetchall()
            col_names = {r[1] for r in cols}
            if "thumbnail_uri" not in col_names:
                conn.execute(text("ALTER TABLE video_assets ADD COLUMN thumbnail_uri VARCHAR(512)"))
                print("Applied migration: video_assets.thumbnail_uri")
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
