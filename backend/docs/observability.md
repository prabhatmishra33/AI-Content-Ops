# Observability Stack

## Implemented
- Structured JSON logging with request correlation id (`x-request-id`)
- Prometheus metrics endpoint: `GET /api/v1/health/metrics`
- HTTP metrics:
  - `http_requests_total`
  - `http_request_latency_seconds`
  - `http_requests_in_progress`
- Queue/task failures persisted to DLQ table and replayable via Ops API

## Dashboard panels (recommended)
- Request rate by endpoint
- Error rate (4xx/5xx) by endpoint
- P95 request latency by endpoint
- Queue backlog / pending tasks by queue
- DLQ new events by task name

## Alert suggestions
- High error rate: `5xx > 2% for 5m`
- Latency spike: `p95 > 2s for 10m`
- Queue backlog: pending tasks above threshold per queue
- LLM outage: repeated `LLM_UNAVAILABLE_HOLD` audit events
- Connector outage: repeated distribution failures on same channel
