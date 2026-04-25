import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

_pattern_engine = None
_PatternSessionLocal = None


def get_pattern_engine():
    global _pattern_engine
    if _pattern_engine is None and settings.pattern_database_url:
        _pattern_engine = create_engine(
            settings.pattern_database_url,
            future=True,
            pool_pre_ping=True,
        )
    return _pattern_engine


def get_pattern_session_factory():
    global _PatternSessionLocal
    engine = get_pattern_engine()
    if engine is None:
        return None
    if _PatternSessionLocal is None:
        _PatternSessionLocal = sessionmaker(
            bind=engine, autocommit=False, autoflush=False, future=True
        )
    return _PatternSessionLocal


def get_pattern_db():
    factory = get_pattern_session_factory()
    if factory is None:
        raise RuntimeError("Pattern DB not configured — set PATTERN_DATABASE_URL")
    db = factory()
    try:
        yield db
    finally:
        db.close()


def init_pattern_db() -> bool:
    """Create all pattern tables and enable pgvector extension. Returns True on success."""
    engine = get_pattern_engine()
    if engine is None:
        logger.warning("PATTERN_DATABASE_URL not set — pattern DB skipped")
        return False
    try:
        from app.db.pattern_base import PatternBase
        import app.models.pattern_entities  # noqa: F401 — registers models

        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()

        PatternBase.metadata.create_all(bind=engine)
        logger.info("Pattern DB tables ready")
        return True
    except Exception as exc:
        logger.error("Pattern DB init failed: %s", exc)
        return False


def is_pattern_db_available() -> bool:
    engine = get_pattern_engine()
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
