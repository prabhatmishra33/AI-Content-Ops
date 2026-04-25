# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Content Ops is an event-driven, multi-agent video content moderation and publishing platform with human-in-the-loop approval gates. Videos move through a 10-step state machine: upload → AI moderation (Phase A) → human review (Gate 1) → AI content creation (Phase B) → human QA (Gate 2) → distribution → report/reward.

## Development Commands

### Backend (FastAPI + Celery)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env    # then fill in API keys

# All-in-one startup (migrates DB, seeds data, starts API + Celery workers)
.\scripts\up.ps1
.\scripts\up.ps1 -NoWorker    # skip Celery workers (sync-only mode)
.\scripts\up.ps1 -NoReload    # disable hot reload

# Other lifecycle scripts
.\scripts\migrate.ps1         # run DB migrations only
.\scripts\seed.ps1            # seed default admin/policies
.\scripts\reset.ps1           # drop DB and storage (destructive)
.\scripts\down.ps1            # stop all services

# Direct uvicorn (without scripts)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger UI: `http://127.0.0.1:8000/docs`  
Health: `http://127.0.0.1:8000/api/v1/health/live`  
Metrics: `http://127.0.0.1:8000/api/v1/health/metrics`

**Redis is required for async Celery tasks:**
```bash
docker run --name local-redis -p 6379:6379 -d redis:7
```

### Frontend (Next.js 15)

```bash
cd ui
npm install
npm run dev        # http://localhost:3000
npm run build
npm run lint       # ESLint
```

Create `ui/.env.local` with:
```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Default login: `admin` / `admin123`

### API Testing

Use the Postman collection at `backend/postman/AI_Content_Ops_Backend.postman_collection.json`. Typical flow: Login → Upload → Phase A → Gate 1 Review → Gate 2 Review → Distribute.

## Architecture

### Workflow State Machine

```
UPLOADED → AI_PHASE_A_DONE → ROUTED → IN_REVIEW_GATE_1 → APPROVED_GATE_1
  → AI_PHASE_B_DONE → IN_REVIEW_GATE_2 → APPROVED_GATE_2
  → DISTRIBUTED → REPORT_READY → REWARD_CREDITED → COMPLETED
```

Terminal states: `REJECTED_GATE_1`, `REJECTED_GATE_2`, `HOLD`, `FAILED`

State transitions are managed in `backend/app/services/workflow_service.py`. The `ProcessingJob` entity in the DB is the authoritative state carrier.

### Multi-Agent AI Pipeline

Agents live in `backend/app/agents/`. Each agent is an independent LLM call:
- `moderation.py` — abuse detection (violence, hate, explicit, etc.)
- `classification.py` — content tagging
- `impact.py` / `direct_impact.py` — impact score (0.0–1.0)
- `compliance.py` — policy violation checks
- `content.py` — content creation & localization
- `reporter.py` — compliance report generation

All agents go through `backend/app/services/model_gateway.py`, which abstracts providers (Gemini, OpenAI-compatible, Ollama) and handles retries. Set `MODEL_PROVIDER` in `.env` to switch providers. Use `MODEL_PROVIDER=none` to run in mock/offline mode.

### Async Task Orchestration

Celery tasks in `backend/app/orchestrator/tasks.py` wrap each workflow phase. The API exposes both sync (`/phase-a`) and async (`/phase-a/async`) endpoints for each phase. Each queue maps to a specific workflow step — queue names are configurable via `QUEUE_*` env vars.

Failed tasks go to the dead letter queue (DLQ); replay them at `POST /ops/dlq/{event_id}/replay`.

### Key Services

| Service | Responsibility |
|---|---|
| `workflow_service.py` | State machine orchestration |
| `model_gateway.py` | LLM provider abstraction & retry |
| `review_service.py` | Human review queue & SLA tracking |
| `audio_news_service.py` | TTS via Gemini Flash for voice output |
| `distribution_service.py` | YouTube OAuth + secondary webhook publishing |
| `audit_service.py` | Immutable append-only event log |
| `idempotency_service.py` | Request deduplication by idempotency key |
| `routing_service.py` | Threshold-based P0/P1/P2 priority assignment |
| `prompt_registry.py` | Versioned prompt management for agents |

### Database

SQLite by default (`DATABASE_URL` in `.env`); swap to PostgreSQL for production. SQLAlchemy 2.0 async ORM. Key tables: `video_assets`, `processing_jobs`, `ai_results`, `review_tasks`, `review_decisions`, `distribution_results`, `audit_events`, `wallet_accounts`, `reward_transactions`, `integration_credentials` (tokens encrypted at rest).

### Frontend Structure

Next.js App Router. Pages under `ui/src/app/`:
- `/dashboard` — stats overview
- `/videos/upload` — file upload (uploader, admin)
- `/reviews/queue` — review queue by priority P0/P1/P2 (moderator, admin)
- `/ops/dlq`, `/ops/policies`, `/ops/distribution` — admin ops

Auth state via Zustand (`ui/src/store/`). API calls via `ui/src/lib/` (TanStack Query for data fetching).

## Key Configuration

All backend config is through `.env`. Important groups:

- **LLM:** `MODEL_PROVIDER`, `GOOGLE_API_KEY`, `MODEL_NAME_*` (per-agent model overrides)
- **Auth:** `AUTH_JWT_SECRET`, `AUTH_DEFAULT_ADMIN_USERNAME/PASSWORD`
- **Queues:** `QUEUE_AI_PROCESSING`, `QUEUE_REVIEW_P0/P1/P2`, etc.
- **YouTube:** `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_STRICT_MODE=false` to skip OAuth in dev
- **Upload limits:** `UPLOAD_MAX_FILE_SIZE_BYTES`, `UPLOAD_ALLOWED_MIME_TYPES`

## RBAC

Three roles: `uploader`, `moderator`, `admin`. JWT-based. Role enforcement is in `backend/app/core/security.py`. Uploaders can upload and track their content; moderators handle review queues; admins access ops and policy management.
