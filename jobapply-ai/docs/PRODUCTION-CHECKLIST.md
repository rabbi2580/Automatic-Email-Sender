# Production checklist

## Before launch
- [ ] `ENVIRONMENT=production`; strong unique `SECRET_KEY`; `ENCRYPTION_KEY` generated, stored in a secret manager/KMS and backed up
- [ ] Managed PostgreSQL with automated backups + point-in-time recovery; `alembic upgrade head` run; restore tested
- [ ] Private S3 bucket, SSE enabled, lifecycle policy, no public ACLs
- [ ] Redis (persistence on); `RATE_LIMIT_BACKEND=redis`; `TASK_MODE=celery`; worker(s) running and monitored
- [ ] TLS everywhere; HSTS; `CORS_ORIGINS`, `API_BASE_URL`, `PUBLIC_BASE_URL` are the real https origins; `TRUSTED_PROXY_HOPS` matches your proxy chain
- [ ] Google OAuth app **verified** for the `gmail.send` sensitive scope (can take weeks); Microsoft app registered; redirect URIs match exactly
- [ ] Transactional SMTP configured with SPF/DKIM/DMARC; verification emails land in inboxes
- [ ] AI provider contract: zero-retention / no-training; per-project spend limits; keys in secret manager
- [ ] Legal: Terms + Privacy Policy reviewed by counsel and linked at signup; sub-processor list; cookie/storage notice; contact for privacy/security
- [ ] First admin created; default plan limits reviewed (`/admin/limits`); send caps reviewed
- [ ] CI: backend tests (SQLite + Postgres), `ruff`, frontend `lint` + `build`, `pip-audit`, `npm audit`, secret scanning, container image scan
- [ ] Monitoring/alerts: API 5xx rate, p95 latency, queue depth, stuck jobs, AI failure rate, send failures, disk/DB size; error tracking (e.g. Sentry) with PII scrubbing
- [ ] Load test bulk intake (30 jobs) and generation under concurrent users; set worker concurrency accordingly
- [ ] Penetration test / security review of items in `docs/SECURITY.md` “Known limitations”
- [ ] Incident runbook: revoke all sessions, rotate keys, disable sending (feature flag/suspend), notify users within legal deadlines

## Operations
- [ ] Weekly: review `/admin/health`, delivery failures, AI cost; monthly: restore drill, dependency updates
- [ ] Retention: purge audit logs > 12 months (job not automated yet); honour deletion requests (self-service exists)
