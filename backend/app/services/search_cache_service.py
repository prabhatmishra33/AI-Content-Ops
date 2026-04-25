import hashlib
import json
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class SearchCacheService:
    """Redis-backed cache for search/grounding results keyed by query hash."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            import redis
            self._client = redis.from_url(settings.redis_url, decode_responses=True)
        return self._client

    @staticmethod
    def _key(query: str) -> str:
        return f"sc:{hashlib.sha256(query.encode()).hexdigest()}"

    def get(self, query: str) -> Optional[dict]:
        if not settings.search_cache_enabled:
            return None
        try:
            raw = self._get_client().get(self._key(query))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("Search cache GET failed: %s", exc)
            return None

    def set(self, query: str, result: dict) -> None:
        if not settings.search_cache_enabled:
            return
        try:
            self._get_client().setex(
                self._key(query),
                settings.search_cache_ttl_seconds,
                json.dumps(result),
            )
        except Exception as exc:
            logger.warning("Search cache SET failed: %s", exc)
