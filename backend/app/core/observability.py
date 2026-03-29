from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response


request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
http_request_latency_seconds = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "In-flight HTTP requests",
    ["method", "path"],
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get("-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        for h in root.handlers:
            h.setFormatter(JsonFormatter())
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


async def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def observability_middleware(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request_id_ctx.set(request_id)
    method = request.method
    path = request.url.path

    http_requests_in_progress.labels(method=method, path=path).inc()
    try:
        response = await call_next(request)
        status_code = str(response.status_code)
        response.headers["x-request-id"] = request_id
        return response
    except Exception:
        status_code = "500"
        raise
    finally:
        duration = time.perf_counter() - started
        http_requests_total.labels(method=method, path=path, status_code=status_code).inc()
        http_request_latency_seconds.labels(method=method, path=path).observe(duration)
        http_requests_in_progress.labels(method=method, path=path).dec()
