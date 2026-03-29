# AI Content Ops UI

Next.js frontend for uploader, moderator, and admin operations against the backend APIs.

## Stack
- Next.js (App Router) + TypeScript
- Tailwind CSS
- TanStack Query
- Zustand

## Prerequisites
- Node.js 20+ (Node 24 also works)
- Backend running at `http://127.0.0.1:8000`

## Setup
```powershell
cd ui
Copy-Item .env.example .env.local
```

## Install
If PowerShell blocks npm scripts, use `npm.cmd`:
```powershell
npm.cmd install
```

## Run
```powershell
npm.cmd run dev
```
Open: `http://127.0.0.1:3000`

## Default Login
- admin / admin123
- moderator / moderator123
- uploader / uploader123

## Main Screens
- `/login`
- `/dashboard`
- `/videos/upload`
- `/videos/[videoId]`
- `/reviews/queue`
- `/reviews/tasks/[taskId]`
- `/ops/policies`
- `/ops/distribution`
- `/ops/dlq`
- `/profile/wallet`

## API Reference
- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## Notes
- Mutating actions use idempotency keys generated in UI.
- Thumbnail visibility depends on backend ffmpeg setup.
