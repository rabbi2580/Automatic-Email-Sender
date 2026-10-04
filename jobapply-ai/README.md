# JobApply AI

**Upload your CV → add job posts → AI analyses everything → review personalised applications → approve → send → track.**

A multi-tenant SaaS: FastAPI + PostgreSQL + Celery/Redis backend, Next.js + TypeScript + Tailwind frontend, S3-compatible storage, and a provider-agnostic AI layer that also runs fully offline with a built-in rule-based ("heuristic") provider.

## Principles enforced in code (not just in prompts)

| Principle | Where it is enforced |
|---|---|
| **Nothing is sent without explicit approval** | `services/delivery/service.py`: application must be `approved`, QC must pass, content hash unchanged since approval, a signed confirmation token bound to the exact previewed content, `confirm=true`, verified email, hourly/daily caps, plan quota |
| **No fabricated CV facts** | Tailored CVs are assembled from profile entities by id; LLM output is grounded against the CV text (`ground_extraction`), rewrites that add skills/numbers are rejected (`rewrite_is_safe`), and an independent QC agent re-verifies every skill/employer/degree/date |
| **Tenant isolation** | Every owned row has `user_id`; all access goes through `get_owned()`; foreign ids return 404; storage keys are `u/{user_id}/…`; automated route sweep in `tests/test_tenant_isolation.py` |
| **Respect sites** | URL intake honours `robots.txt`, refuses login-walled hosts (LinkedIn/Facebook), is SSRF-safe; no CAPTCHA/login bypass; URL-only jobs are *assisted* (link + prepared materials + "I applied manually") |
| **Encryption** | OAuth tokens and SMTP passwords are Fernet-encrypted; TLS + HSTS in production; signed short-lived file URLs; Argon2id passwords |
| **Privacy** | Export (JSON), delete application history, delete account (cascade + file purge), AI-training opt-in off by default, admin APIs expose metadata only |

## Quick start (development, no Docker, no API keys)

```bash
# backend  (Python 3.11+)
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000                  # SQLite + local storage + inline tasks by default
# → http://localhost:8000/docs

# frontend  (Node 20+)
cd frontend
cp .env.example .env.local
npm install && npm run dev                                 # → http://localhost:3000
```

In development, verification links are written to the API log (no SMTP needed). With `AI_PROVIDER=heuristic` everything works offline; set `AI_PROVIDER=openai|anthropic|gemini|openai_compatible` plus a key for higher-quality extraction and writing.

## Docker (Postgres, Redis, MinIO, API, Celery worker, web)

```bash
cp .env.example .env     # fill SECRET_KEY, ENCRYPTION_KEY, POSTGRES_PASSWORD, S3_* (commands are in the file)
docker compose up --build
```

See [`docs/05-setup-and-deployment.md`](docs/05-setup-and-deployment.md) for production guidance.

## Tests

```bash
cd backend && python -m pytest -q                                   # SQLite (default)
TEST_DATABASE_URL=postgresql+psycopg2://user:pw@localhost/db python -m pytest -q   # against Postgres
cd frontend && npm run lint && npm run build
```

163 automated tests cover parsing, matching, generation, QC, AI-service safety, auth, tenant isolation, send safeguards, privacy, input safety, job intake and the full upload → 20 jobs → match → generate → approve → send → track flow.

## Documentation

| Doc | Contents |
|---|---|
| [01 Requirements & risks](docs/01-requirements-and-risks.md) | Requirements, ambiguities + decisions, risks, MVP scope |
| [02 Architecture](docs/02-architecture.md) | Diagram, modules, lifecycle, tenancy |
| [03 Database schema](docs/03-database-schema.md) | All 37 tables |
| [04 API reference](docs/04-api-reference.md) | Endpoint map (full OpenAPI at `/docs`) |
| [05 Setup & deployment](docs/05-setup-and-deployment.md) | Env vars, OAuth setup, Docker, production notes |
| [06 AI architecture](docs/06-ai-architecture.md) | Agents, routing, caching, safety, matching formula |
| [SECURITY](docs/SECURITY.md) | Threat model, controls, known limitations |
| [PRIVACY](docs/PRIVACY.md) | Data inventory, retention, user rights, sub-processors |
| [Production checklist](docs/PRODUCTION-CHECKLIST.md) | Go-live checklist |
| [Roadmap](docs/ROADMAP.md) | MVP → Phase 2 → Phase 3 |
| [Legal templates](docs/legal/) | Terms of Service + Privacy Policy **templates — must be reviewed by counsel** |

## Layout

```
backend/   FastAPI app, services, Celery tasks, Alembic migrations, tests
frontend/  Next.js app (dashboard, profile, CVs, jobs wizard, matches, review/approve/send, tracker, email, settings, privacy, admin)
docs/      design + operations docs
docker-compose.yml, .env.example
```
### Operational workers

Production deployments should run both the Celery worker and beat scheduler after `alembic upgrade head`. Beat polls opted-in mailboxes and creates due reminder notifications; neither task sends user email automatically.
