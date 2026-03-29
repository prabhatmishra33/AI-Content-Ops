# AI Content Ops Backend (Phase 1 Implementation)

This backend implements the core end-to-end workflow discussed in the design:

1. Video upload completion (auto Phase-A enqueue)
2. AI phase A (moderation, classification, impact scoring, compliance)
3. Routing to priority queue
4. Human review gate 1
5. AI phase B (content creation + localization)
6. Human review gate 2
7. Distribution (YouTube + real secondary webhook connector)
8. Report generation
9. Reward crediting
10. Audit events

## Stack

- FastAPI
- SQLAlchemy
- SQLite (default)
- Celery + Redis (async orchestration ready)
- LangChain model runtime (provider adapters)
- Modular service + agent architecture (swappable)

## Run locally

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Optional but recommended for thumbnail extraction:
- Install `ffmpeg` and ensure it is available on PATH.

Copy environment template before first run:

```powershell
Copy-Item .env.example .env
```

LangChain provider packages are installed via `requirements.txt`:
- `langchain-core`
- `langchain-openai`
- `langchain-google-genai`
- `langchain-ollama`

## One-command local scripts

From `backend`:

```powershell
.\scripts\setup.ps1
.\scripts\up.ps1
```

Useful startup options:

```powershell
.\scripts\up.ps1 -NoWorker
.\scripts\up.ps1 -NoReload
.\scripts\up.ps1 -AiQueue q.ai_processing
```

Optional helpers:

```powershell
.\scripts\migrate.ps1
.\scripts\seed.ps1
.\scripts\run-demo.ps1 -FilePath "C:\path\to\video.mp4"
.\scripts\reset.ps1
.\scripts\down.ps1
```

`run-demo.ps1` uses auto Phase-A by default. Use `-ManualMode` to force explicit Phase-A call.

Open:

- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/v1/health/live`
- Metrics: `http://127.0.0.1:8000/api/v1/health/metrics`

## Optional async worker setup

Start Redis (required for async endpoints):

```powershell
docker run --name local-redis -p 6379:6379 -d redis:7
```

Start dedicated workers (recommended):

```powershell
.\scripts\up.ps1
```

Manual queue-specific worker example:

```powershell
celery -A app.orchestrator.tasks worker --pool=solo --concurrency=1 -Q q.review,q.review_p0,q.review_p1,q.review_p2,q.hold --loglevel=info
```

## Auth / RBAC

Login and get bearer token:

```http
POST /api/v1/auth/login
{
  "username": "admin",
  "password": "******"
}
```

Roles:
- `uploader`: upload/status/wallet/read outputs
- `moderator`: review decisions, workflow progress
- `admin`: policies, ops replay, connector config/status

## YouTube OAuth configuration (for real publish)

Set these in `.env` inside `backend`:

```env
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret
YOUTUBE_REDIRECT_URI=http://127.0.0.1:8000/api/v1/distribution/youtube/oauth/callback
YOUTUBE_STRICT_MODE=false
```

OAuth steps:

1. `GET /api/v1/distribution/youtube/oauth/url`
2. Open `auth_url` in browser and grant access.
3. Callback stores access/refresh token in DB.
4. Check: `GET /api/v1/distribution/youtube/integration/status`
5. Manual publish: `POST /api/v1/distribution/youtube/publish/{video_id}`
6. Poll status: `GET /api/v1/distribution/youtube/status/{external_id}`
7. Quota status: `GET /api/v1/distribution/youtube/quota`

## LLM / Model gateway configuration

Set these in `.env` to enable real model calls for agents:

```env
MODEL_PROVIDER=openai_compatible
MODEL_API_BASE=https://api.openai.com/v1
MODEL_API_KEY=your_key_here
MODEL_NAME_IMPACT=gpt-4o-mini
MODEL_NAME_MODERATION=gpt-4o-mini
MODEL_NAME_CLASSIFICATION=gpt-4o-mini
MODEL_NAME_COMPLIANCE=gpt-4o-mini
MODEL_NAME_CONTENT=gpt-4o-mini
MODEL_NAME_LOCALIZATION=gpt-4o-mini
MODEL_NAME_REPORTER=gpt-4o-mini
IMPACT_CONFIDENCE_MIN=0.60
MODEL_RETRY_MAX_ATTEMPTS=4
MODEL_RETRY_BACKOFF_INITIAL_SECONDS=1.0
MODEL_RETRY_BACKOFF_MULTIPLIER=2.0
MODEL_RETRY_BACKOFF_MAX_SECONDS=20.0
```

Alternative local provider:

```env
MODEL_PROVIDER=ollama
MODEL_API_BASE=http://127.0.0.1:11434
```

Gemini Flash Preview provider:

```env
MODEL_PROVIDER=gemini
# LangChain doc convention:
GOOGLE_API_KEY=your_google_ai_studio_key
MODEL_API_BASE=https://generativelanguage.googleapis.com/v1beta
MODEL_NAME_IMPACT=gemini-2.0-flash-preview
MODEL_NAME_MODERATION=gemini-2.0-flash-preview
MODEL_NAME_CLASSIFICATION=gemini-2.0-flash-preview
MODEL_NAME_COMPLIANCE=gemini-2.0-flash-preview
MODEL_NAME_CONTENT=gemini-2.0-flash-preview
MODEL_NAME_LOCALIZATION=gemini-2.0-flash-preview
MODEL_NAME_REPORTER=gemini-2.0-flash-preview
```

Note: model IDs can vary by account/region. If you get model-not-found, update to the exact Gemini Flash Preview model name enabled for your key.
For compatibility, backend also accepts `GEMINI_API_KEY` or `MODEL_API_KEY` as fallback.

LLM calls use exponential backoff retries on transient failures (`429`, `5xx`, timeout, connection errors).  
If all retries fail, the workflow moves the job to `HOLD` with `last_error` and an audit event.

## Suggested demo sequence

1. Upload video:
   - `POST /api/v1/videos/upload/file` (multipart form-data)
   - fields:
     - `uploader_ref` (text)
     - `file` (file)
     - optional `idempotency_key` (text)
2. Alternative metadata-only registration:
   - `POST /api/v1/videos/upload/complete`
3. Phase A auto-starts after upload enqueue.
   - Manual retry endpoints still available:
   - `POST /api/v1/workflow/{job_id}/phase-a`
   - `POST /api/v1/workflow/{job_id}/phase-a/async`
3. `POST /api/v1/workflow/{job_id}/gate-1/create`
   - if HOLD state: `POST /api/v1/workflow/{job_id}/hold/escalate`
4. `POST /api/v1/reviews/tasks/{task_id}/decision` with `APPROVE`
5. `POST /api/v1/workflow/{job_id}/gate-1/handle`
6. `POST /api/v1/workflow/{job_id}/gate-2/create`
7. `POST /api/v1/reviews/tasks/{task_id}/decision` with `APPROVE`
8. `POST /api/v1/workflow/{job_id}/finalize`
9. Check outputs:
   - `GET /api/v1/ai-results/video/{video_id}`
   - `GET /api/v1/policies/active`
   - `GET /api/v1/reports/video/{video_id}`
   - `GET /api/v1/distribution/video/{video_id}`
   - `GET /api/v1/wallet/{uploader_ref}`
   - `GET /api/v1/audit/job/{job_id}`
   - `GET /api/v1/workflow/tasks/{task_id}/status` (for async task status)

## Review workflow maturity endpoints

- `POST /api/v1/reviews/tasks/{task_id}/claim?reviewer_ref=moderator_1`
- `POST /api/v1/reviews/tasks/{task_id}/release`
- `POST /api/v1/reviews/tasks/{task_id}/escalate?to_priority=P0&escalated_by=lead_1&reason=urgent`
- `POST /api/v1/reviews/tasks/{task_id}/reopen?reviewer_ref=lead_1&notes=recheck`
- `GET /api/v1/reviews/sla/breaches`

## DLQ operations

- `GET /api/v1/ops/dlq`
- `POST /api/v1/ops/dlq/{event_id}/replay`

## Runbooks

- [Failure Runbooks](docs/failure-runbooks.md)
- [Observability Notes](docs/observability.md)

## Notes

- Secondary channel is a real webhook connector with retries.
- YouTube connector includes OAuth token refresh, token encryption-at-rest (when key is configured), quota consumption tracking, and status polling endpoint.
- Multipart uploaded files are stored locally under `backend/storage/uploads`.
- Generated thumbnails are stored under `backend/storage/thumbnails` (when `ffmpeg` is available).
