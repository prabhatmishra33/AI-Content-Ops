# UI Screens and Actions (Implemented)

This document maps the implemented UI to backend Swagger APIs.

Backend Swagger: `http://127.0.0.1:8000/docs`

## 1) Login (`/login`)
### Actions
- Login with username/password
### APIs
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me` (optional session verify)

## 2) Dashboard (`/dashboard`)
### Actions
- Role-aware quick links
- Pending review count
- Wallet snapshot
### APIs
- `GET /api/v1/reviews/tasks?status=PENDING`
- `GET /api/v1/wallet/{uploader_ref}`

## 3) Upload (`/videos/upload`)
### Actions
- Upload local video file
- Capture `video_id`, `job_id`, `thumbnail_uri`
- Render thumbnail + video preview (when available)
- Navigate to video timeline page
### APIs
- `POST /api/v1/videos/upload/file`
- `GET /api/v1/videos/{video_id}/thumbnail`
- `GET /api/v1/videos/{video_id}/stream`

## 4) Video Timeline (`/videos/{videoId}`)
### Actions
- View current state, priority, errors
- View timeline from audit events
- View AI outputs, distribution status, report summary
- View thumbnail and playable video preview
### APIs
- `GET /api/v1/videos/{video_id}`
- `GET /api/v1/videos/{video_id}/status`
- `GET /api/v1/videos/{video_id}/thumbnail`
- `GET /api/v1/videos/{video_id}/stream`
- `GET /api/v1/ai-results/video/{video_id}`
- `GET /api/v1/distribution/video/{video_id}`
- `GET /api/v1/reports/video/{video_id}`
- `GET /api/v1/audit/job/{job_id}`

## 5) Review Queue (`/reviews/queue`)
### Actions
- Filter by gate/status
- Claim task
- Open task detail or linked video
### APIs
- `GET /api/v1/reviews/tasks`
- `POST /api/v1/reviews/tasks/{task_id}/claim`

## 6) Review Task Detail (`/reviews/tasks/{taskId}`)
### Actions
- View task + AI context
- Submit approve/reject with notes
### APIs
- `GET /api/v1/reviews/tasks`
- `GET /api/v1/ai-results/video/{video_id}`
- `POST /api/v1/reviews/tasks/{task_id}/decision`

## 7) Policy Ops (`/ops/policies`)
### Actions
- View active policy
- Activate new policy thresholds
### APIs
- `GET /api/v1/policies/active`
- `POST /api/v1/policies/activate`

## 8) Distribution Ops (`/ops/distribution`)
### Actions
- Open YouTube OAuth URL
- Check integration status and quota
- Trigger manual publish
- Poll external status
### APIs
- `GET /api/v1/distribution/youtube/oauth/url`
- `GET /api/v1/distribution/youtube/integration/status`
- `GET /api/v1/distribution/youtube/quota`
- `POST /api/v1/distribution/youtube/publish/{video_id}`
- `GET /api/v1/distribution/youtube/status/{external_id}`

## 9) DLQ Ops (`/ops/dlq`)
### Actions
- List dead-letter events
- Replay failed event
### APIs
- `GET /api/v1/ops/dlq`
- `POST /api/v1/ops/dlq/{event_id}/replay`

## 10) Wallet (`/profile/wallet`)
### Actions
- View balance and reward transactions
### APIs
- `GET /api/v1/wallet/{uploader_ref}`

## Concurrency/State Notes
- Queue page polls every 5s to reflect multi-moderator updates.
- Decision/claim actions send idempotency keys from UI.
- Backend remains source of truth for claim/decision conflict resolution.
