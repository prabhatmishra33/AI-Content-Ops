from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Tuple

from app.core.config import settings


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            raise ValueError("No JSON object found in model response")
        return json.loads(m.group(0))


class ModelGateway:
    @staticmethod
    def _backoff_seconds(attempt: int) -> float:
        seconds = settings.model_retry_backoff_initial_seconds * (
            settings.model_retry_backoff_multiplier ** (attempt - 1)
        )
        return min(seconds, settings.model_retry_backoff_max_seconds)

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        transient_markers = [
            "timeout",
            "temporarily unavailable",
            "connection",
            "rate limit",
            "429",
            "500",
            "502",
            "503",
            "504",
        ]
        return any(marker in msg for marker in transient_markers)

    @staticmethod
    def _make_model(model: str):
        provider = settings.model_provider

        if provider == "openai_compatible":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as exc:
                raise RuntimeError("langchain-openai is not installed") from exc
            if not settings.model_api_base:
                raise ValueError("MODEL_API_BASE is required for openai_compatible provider")
            if not settings.model_api_key:
                raise ValueError("MODEL_API_KEY is required for openai_compatible provider")
            return ChatOpenAI(
                model=model,
                temperature=settings.model_temperature,
                api_key=settings.model_api_key,
                base_url=settings.model_api_base,
                timeout=settings.model_timeout_seconds,
            )

        if provider == "gemini":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as exc:
                raise RuntimeError("langchain-google-genai is not installed") from exc
            # Follow LangChain docs convention first (GOOGLE_API_KEY),
            # then allow legacy/local fallbacks.
            api_key = settings.google_api_key or settings.gemini_api_key or settings.model_api_key
            if not api_key:
                raise ValueError("GOOGLE_API_KEY (or GEMINI_API_KEY / MODEL_API_KEY) is required for gemini provider")
            return ChatGoogleGenerativeAI(
                model=model,
                temperature=settings.model_temperature,
                google_api_key=api_key,
                timeout=settings.model_timeout_seconds,
                max_retries=0,  # retries are handled by ModelGateway exponential backoff
            )

        if provider == "ollama":
            try:
                from langchain_ollama import ChatOllama
            except ImportError as exc:
                raise RuntimeError("langchain-ollama is not installed") from exc
            base_url = settings.model_api_base or "http://127.0.0.1:11434"
            return ChatOllama(
                model=model,
                temperature=settings.model_temperature,
                base_url=base_url,
            )

        raise ValueError("Model provider is disabled or not configured")

    async def _invoke_with_backoff(self, model: str, system: str, user: str) -> Tuple[str, dict]:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError as exc:
            raise RuntimeError("langchain-core is not installed") from exc

        chat_model = self._make_model(model)
        messages = [SystemMessage(content=system), HumanMessage(content=user)]

        start = time.perf_counter()
        last_exc: Exception | None = None
        for attempt in range(1, settings.model_retry_max_attempts + 1):
            try:
                result = await chat_model.ainvoke(messages)
                latency_ms = int((time.perf_counter() - start) * 1000)
                return str(result.content), {
                    "provider": settings.model_provider,
                    "model": model,
                    "latency_ms": latency_ms,
                    "fallback_used": False,
                    "retry_max_attempts": settings.model_retry_max_attempts,
                    "attempts_used": attempt,
                    "framework": "langchain",
                }
            except Exception as exc:
                last_exc = exc
                if attempt >= settings.model_retry_max_attempts or not self._is_transient_error(exc):
                    raise
                await asyncio.sleep(self._backoff_seconds(attempt))
        if last_exc:
            raise last_exc
        raise RuntimeError("Unexpected LangChain invocation failure")

    async def generate_json(self, model: str, system: str, user: str) -> Tuple[dict, dict]:
        text, meta = await self._invoke_with_backoff(
            model=model,
            system=system,
            user=f"{user}\n\nReturn valid JSON only.",
        )
        parsed = _extract_json(text)
        return parsed, meta

    async def generate_text(self, model: str, system: str, user: str) -> Tuple[str, dict]:
        text, meta = await self._invoke_with_backoff(model=model, system=system, user=user)
        return text, meta
