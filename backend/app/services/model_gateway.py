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
            # For Gemini, we now use the native google-genai SDK via our central utility
            # to support forced Vertex AI backend for text processing.
            from app.core.genai_client import get_genai_client
            client = get_genai_client(force_vertexai=True)
            return client

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
        chat_model = self._make_model(model)
        provider = settings.model_provider
        
        # Determine if we are using the native google-genai client
        from google import genai
        is_native_gemini = provider == "gemini" and isinstance(chat_model, genai.Client)

        start = time.perf_counter()
        last_exc: Exception | None = None
        
        for attempt in range(1, settings.model_retry_max_attempts + 1):
            try:
                if is_native_gemini:
                    # Native google-genai path
                    from google.genai import types
                    response = chat_model.models.generate_content(
                        model=model,
                        contents=user,
                        config=types.GenerateContentConfig(
                            system_instruction=system,
                            temperature=settings.model_temperature,
                        )
                    )
                    content = response.text
                    framework = "native"
                else:
                    # LangChain path for other providers
                    from langchain_core.messages import HumanMessage, SystemMessage
                    messages = [SystemMessage(content=system), HumanMessage(content=user)]
                    result = await chat_model.ainvoke(messages)
                    content = str(result.content)
                    framework = "langchain"

                latency_ms = int((time.perf_counter() - start) * 1000)
                return content, {
                    "provider": provider,
                    "model": model,
                    "latency_ms": latency_ms,
                    "fallback_used": False,
                    "retry_max_attempts": settings.model_retry_max_attempts,
                    "attempts_used": attempt,
                    "framework": framework,
                }
            except Exception as exc:
                last_exc = exc
                if attempt >= settings.model_retry_max_attempts or not self._is_transient_error(exc):
                    raise
                await asyncio.sleep(self._backoff_seconds(attempt))
        
        if last_exc:
            raise last_exc
        raise RuntimeError("Unexpected model invocation failure")

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
