# Security

## Threat model (summary)
Assets: CV/personal data, OAuth tokens & SMTP passwords (can send mail as the user), session tokens. Adversaries: other tenants, anonymous internet, malicious job posts/CVs (prompt injection, SSRF, malicious files), a compromised LLM provider response, an abusive user (spam), a curious operator.

## Controls implemented (and where)
| Area | Control |
|---|---|
| Passwords | Argon2id; min length 10; per-IP rate limit on auth routes; per-account lockout after 10 failures / 15 min |
| Sessions | 15-min access JWT; 30-day rotating refresh tokens stored hashed; **reuse of a rotated token revokes the whole family**; password change revokes other sessions; logout revokes the family |
| Authorization | Single `get_owned()` path; foreign resources → 404; `require_admin` for `/admin/*`; sweep test proves every route rejects anonymous calls and every owned resource is invisible to other users |
| Secrets | OAuth tokens/SMTP passwords Fernet-encrypted at rest, never returned by any endpoint; production refuses weak `SECRET_KEY`/missing `ENCRYPTION_KEY`; logs scrub secrets and carry no CV/job content; AI logs are metadata-only |
| Sending safety | Approval + QC pass + unchanged content hash + signed confirmation token bound to content + `confirm=true` + verified email + hourly/daily caps + plan quota + idempotency + `needs_reauth` handling; Gmail/Outlook scopes are send-only |
| Uploads | size caps, magic-byte sniffing (extension and client MIME are not trusted), random storage keys, parsing never executes content, executables rejected |
| URL intake | SSRF guard (DNS resolved then checked against private/loopback/link-local/metadata ranges, redirects re-validated, size/time caps), `robots.txt` honoured, login-walled hosts refused |
| LLM safety | untrusted-text delimiting + rules, strict schema validation, no tool use, grounding against source text, QC link/address allow-list (only URLs/addresses from the profile or job post may appear in letters/emails) |
| Files | downloads only via short-lived (5 min) HMAC-signed, user-bound URLs; storage private |
| HTTP | HSTS (production), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, API CSP `default-src 'none'`, CORS limited to the web origin, bearer tokens (no cookies → no CSRF surface) |
| Abuse | rate limits (memory or Redis), per-user send caps, quotas, suspend user + feature flags in admin, audit log of security-relevant actions |
| Privacy | export, delete history, delete account (DB cascade + file purge); admin endpoints return aggregates/metadata only (tested) |

## Known limitations / hardening backlog (be aware before launch)
1. **Tokens live in `localStorage`** in the web app, so an XSS bug could steal them. The app renders no raw HTML and sets no `dangerouslySetInnerHTML`, but the stronger design is httpOnly, SameSite cookies via a Next.js BFF — recommended before handling large user volumes. A strict CSP for the web app should be added at the proxy once asset origins are final.
2. **No MFA** yet. Recommended for accounts that connect email.
3. **No antivirus scan** of uploads (type sniffing only). Add ClamAV in the worker for public launch.
4. **No Postgres row-level security**; isolation is enforced in application code and tests. RLS (`user_id = current_setting('app.user_id')`) is a defence-in-depth option.
5. **Encryption key rotation** is manual (`MultiFernet` + re-encrypt script not yet provided). Use a KMS-managed key for `ENCRYPTION_KEY`.
6. Files are stored as uploaded; enable server-side encryption on the bucket. Field-level encryption of CV text in the DB is not implemented (rely on volume/DB encryption).
7. The heuristic parsers are not a security boundary; always keep QC enabled.
8. Rate limiting without Redis is per process. Use `RATE_LIMIT_BACKEND=redis` with multiple replicas.
9. Penetration test, dependency scanning (`pip-audit`, `npm audit`) and secret scanning in CI are not set up here.

## Reporting
Publish a `security@` address and a disclosure policy before launch.
Mailbox tracking uses a separate read-only OAuth scope and is disabled by default. Every tracking query is constrained to addresses used by the user’s sent applications, and all stored records carry the owning user id. Follow-up sending still requires an explicit user-authored approval and the existing delivery safeguards.
