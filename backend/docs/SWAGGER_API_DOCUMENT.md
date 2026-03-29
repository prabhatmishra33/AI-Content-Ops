# AI Content Ops Backend - Swagger API Document

## 1. Live Swagger/OpenAPI
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## 2. Auth Model
- Scheme: `Bearer` JWT
- Login endpoint returns token:
  - `POST /api/v1/auth/login`
- Roles:
  - `uploader`
  - `moderator`
  - `admin`

## 3. Global Headers
- `Authorization: Bearer <token>` for protected APIs
- `x-idempotency-key: <unique-key>` for mutating APIs (recommended)
- `x-webhook-secret: <secret>` for YouTube webhook (if configured)

## 4. Endpoint Groups

### 4.1 Auth
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

### 4.2 Health & Observability
- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- `GET /api/v1/health/metrics`

### 4.3 Videos
- `POST /api/v1/videos/upload/file`
  - multipart: `uploader_ref`, `file`, optional `idempotency_key`
  - includes `thumbnail_uri` in response
- `POST /api/v1/videos/upload/complete`
- `GET /api/v1/videos/{video_id}`
- `GET /api/v1/videos/{video_id}/status`
- `GET /api/v1/videos/{video_id}/thumbnail`
- `GET /api/v1/videos/{video_id}/stream`

### 4.4 Workflow
- `POST /api/v1/workflow/{job_id}/phase-a`
- `POST /api/v1/workflow/{job_id}/phase-a/async`
- `POST /api/v1/workflow/{job_id}/gate-1/create`
- `POST /api/v1/workflow/{job_id}/gate-1/create/async`
- `POST /api/v1/workflow/{job_id}/hold/escalate`
- `POST /api/v1/workflow/{job_id}/gate-1/handle`
- `POST /api/v1/workflow/{job_id}/gate-1/handle/async`
- `POST /api/v1/workflow/{job_id}/gate-2/create`
- `POST /api/v1/workflow/{job_id}/gate-2/create/async`
- `POST /api/v1/workflow/{job_id}/finalize`
- `POST /api/v1/workflow/{job_id}/finalize/async`
- `GET /api/v1/workflow/tasks/{task_id}/status`

### 4.5 Reviews
- `GET /api/v1/reviews/tasks`
- `POST /api/v1/reviews/tasks/{task_id}/decision`
- `POST /api/v1/reviews/tasks/{task_id}/claim`
- `POST /api/v1/reviews/tasks/{task_id}/release`
- `POST /api/v1/reviews/tasks/{task_id}/escalate`
- `POST /api/v1/reviews/tasks/{task_id}/reopen`
- `GET /api/v1/reviews/sla/breaches`

### 4.6 AI / Reports / Wallet / Audit
- `GET /api/v1/ai-results/video/{video_id}`
- `GET /api/v1/reports/video/{video_id}`
- `GET /api/v1/wallet/{uploader_ref}`
- `GET /api/v1/audit/{entity_type}/{entity_id}`

### 4.7 Policies
- `GET /api/v1/policies/active`
- `POST /api/v1/policies/activate`

### 4.8 Distribution
- `GET /api/v1/distribution/video/{video_id}`
- `GET /api/v1/distribution/youtube/oauth/url`
- `GET /api/v1/distribution/youtube/oauth/callback`
- `POST /api/v1/distribution/youtube/publish/{video_id}`
- `GET /api/v1/distribution/youtube/integration/status`
- `GET /api/v1/distribution/youtube/quota`
- `GET /api/v1/distribution/youtube/status/{external_id}`
- `POST /api/v1/distribution/youtube/webhook`

### 4.9 Ops (DLQ)
- `GET /api/v1/ops/dlq`
- `POST /api/v1/ops/dlq/{event_id}/replay`

## 5. Recommended Demo Sequence
1. Login: `POST /api/v1/auth/login`
2. Upload: `POST /api/v1/videos/upload/file`
3. Check status: `GET /api/v1/videos/{video_id}/status`
4. If HOLD, escalate: `POST /api/v1/workflow/{job_id}/hold/escalate`
5. Approve Gate 1 and Gate 2 via review decision APIs
6. Read outputs:
   - AI result
   - report
   - distribution status
   - wallet
   - audit trail

## 6. Idempotency Notes
- Same `x-idempotency-key` + same endpoint scope returns cached prior response.
- Use a new key for each new business operation.
- Review decisions are scoped by task id to prevent gate-mix replay.
