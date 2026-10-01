# 05 — Setup and deployment

## 1. Configuration (environment variables)
All settings are read by `backend/app/core/config.py`. `.env.example` lists every variable; the important ones:

| Variable | Notes |
|---|---|
| `ENVIRONMENT` | `development` creates tables automatically; `production` **refuses to start** without a strong `SECRET_KEY` (≥32 chars) and an `ENCRYPTION_KEY`, and relies on Alembic |
| `SECRET_KEY` | signs JWTs, download URLs, confirmation tokens, OAuth state |
| `ENCRYPTION_KEY` | Fernet key for OAuth tokens/SMTP passwords. **Back it up; losing it forces every user to reconnect email.** Rotating requires re-encryption |
| `DATABASE_URL` | `postgresql+psycopg2://…` in production |
| `TASK_MODE` | `inline` (dev/tests) or `celery` (production; needs Redis + a worker) |
| `STORAGE_BACKEND` | `local` or `s3` (`S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`) |
| `RATE_LIMIT_BACKEND` | `redis` whenever more than one API process/replica runs |
| `TRUSTED_PROXY_HOPS` | number of reverse proxies you control in front of the API (client IP for rate limits/audit comes from `X-Forwarded-For` only when > 0) |
| `AI_PROVIDER` | `heuristic` \| `openai` \| `openai_compatible` \| `anthropic` \| `gemini`; plus `AI_CHEAP_MODEL`, `AI_STRONG_MODEL` |

## 2. OAuth setup
* **Google** (sign-in and Gmail send): create an OAuth client; authorised redirect URIs: `{API_BASE_URL}/api/v1/auth/google/callback` and `{API_BASE_URL}/api/v1/integrations/email/callback/gmail`. The Gmail scope requested is `gmail.send` only. This is a *sensitive* scope: Google requires app verification before public launch.
* **Microsoft** (Outlook send): register an app; redirect URI `{API_BASE_URL}/api/v1/integrations/email/callback/outlook`; delegated permission `Mail.Send` + `offline_access`.
* **SMTP**: users enter their own host/credentials; passwords are encrypted and never returned by the API.

## 3. Docker Compose
`docker compose up --build` starts Postgres, Redis, MinIO (+ bucket creation), the API (runs `alembic upgrade head` on start), a Celery worker and the web app. The backend image installs pango + Noto fonts (Bangla PDFs) and Tesseract (OCR; English + Bangla).
> The Compose file and Dockerfiles were written and statically reviewed but not executed in the authoring environment (no Docker daemon); the same code was exercised against a real PostgreSQL 16 and Redis. Run a first `docker compose build` before relying on them.

## 4. Production notes
* Terminate TLS at a proxy/load balancer; set `API_BASE_URL`/`PUBLIC_BASE_URL` to the https URLs and `CORS_ORIGINS` to the web origin only.
* Use managed Postgres (backups + PITR), managed Redis, and S3 with server-side encryption and a private bucket (the app only hands out short-lived signed URLs through the API).
* Run ≥2 API replicas and ≥1 worker; scale workers on queue depth.
* Ship JSON logs (they scrub secrets and contain no CV/job content) to your log platform; alert on `/api/v1/admin/health` fields (`stuck_jobs`, `ai_failure_rate_24h`, failed sends).
* Create the first admin: `UPDATE users SET role='admin' WHERE email='you@example.com';`
* Migrations: `cd backend && alembic upgrade head`. Create new ones with `alembic revision --autogenerate -m "…"`, review them, and run `alembic check` in CI.
