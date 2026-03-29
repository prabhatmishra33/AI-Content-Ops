# Failure Runbooks

## 1) LLM outage / invalid key
- Symptoms: audit event `LLM_UNAVAILABLE_HOLD`, jobs remain `HOLD`, worker logs show provider auth or timeout errors.
- Verify:
  - `GET /api/v1/videos/{video_id}/status`
  - `GET /api/v1/audit/job/{job_id}`
  - check `.logs/celery.ai.err.log`
- Recovery:
  - fix model credentials/config in `.env`
  - restart API and AI worker
  - replay failed tasks through `POST /api/v1/ops/dlq/{event_id}/replay`

## 2) Redis outage
- Symptoms: enqueue failures (`PHASE_A_ENQUEUE_FAILED`), workers disconnected.
- Verify:
  - `redis-cli ping` (or equivalent)
  - API `.logs/api.err.log`, worker logs
- Recovery:
  - start Redis
  - restart workers (`scripts/down.ps1`, `scripts/up.ps1`)
  - replay DLQ events

## 3) Queue backlog (review/report/reward/distribution)
- Symptoms: task status remains `PENDING`, delayed state transitions.
- Verify:
  - `GET /api/v1/workflow/tasks/{task_id}/status`
  - queue-specific worker logs:
    - `.logs/celery.review.out.log`
    - `.logs/celery.distribution.out.log`
    - `.logs/celery.report.out.log`
    - `.logs/celery.reward.out.log`
- Recovery:
  - scale workers for impacted queues
  - for Windows local demo run additional solo workers on same queue
  - replay stuck/failure tasks from DLQ

## 4) YouTube connector outage / quota
- Symptoms: distribution status `FAILED`, error reason includes quota/token/API error.
- Verify:
  - `GET /api/v1/distribution/video/{video_id}`
  - `GET /api/v1/distribution/youtube/integration/status`
  - `GET /api/v1/distribution/youtube/status/{external_id}`
- Recovery:
  - refresh OAuth token (reauthorize)
  - wait for quota window reset
  - retry publish endpoint with idempotency key for safe retries

## 5) Secondary channel connector outage
- Symptoms: secondary distribution `FAILED`, retries exhausted.
- Verify:
  - inspect distribution results
  - inspect downstream webhook endpoint health
- Recovery:
  - restore secondary webhook availability
  - replay distribution task from DLQ

## 6) Security upload rejections
- Symptoms: upload API returns 400 with MIME/size/malware details.
- Verify:
  - file size and MIME signature
  - malware scan endpoint configuration
- Recovery:
  - upload supported formats only
  - fix malware scanner connectivity / API key
