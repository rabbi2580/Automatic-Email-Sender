# Privacy design

## Data inventory
| Data | Purpose | Where | Retention |
|---|---|---|---|
| Account (email, name, password hash, locale) | authentication | `users` | until account deletion |
| CV file + extracted text + structured profile | build profile, tailor applications | object storage `u/{user}/…`, `resumes`, `profile*` | until the user deletes the CV / account |
| Job posts (original text/files, parsed fields) | matching, tailoring | `jobs`, storage | until the user deletes the job / account |
| Generated CV/letter/email, send log | review, tracking, proof of delivery | `applications*`, storage | until the user deletes history / account |
| Email credentials (OAuth refresh token / SMTP password) | send mail on user's behalf after approval | `email_accounts` (Fernet-encrypted) | until disconnect / account deletion |
| Audit log (action, IP, timestamp — no content) | security | `audit_logs` | recommended: 12 months, then purge (job not yet automated) |
| AI request log (task, model, tokens, latency) — no content | cost + reliability | `ai_request_logs` | metadata only; identity detached on account deletion |

## User rights, implemented
* **Access / portability**: `GET /privacy/export` (JSON of profile, CV text, jobs, matches, applications, letters, emails; credentials excluded).
* **Erasure**: `DELETE /privacy/account` (typed confirmation; cascades through all owned tables and deletes stored files); `DELETE /privacy/application-history`; per-CV and per-job delete.
* **Consent**: terms + AI-disclosure consent at signup (timestamped); explicit consent before connecting an email account; a confirmation checkbox before every send.
* **AI training**: the service never uses user data to train models. A user-level opt-in flag exists (default **off**) and is exported; no pipeline consumes it today.
* **Transparency**: the UI states that drafts are AI-generated, that scores are estimates, and which provider processes text when an external AI is configured.

## Sub-processors (depending on your configuration)
AI provider (OpenAI/Anthropic/Google/self-hosted), cloud host + managed Postgres/Redis, object storage, transactional email provider, Google/Microsoft (OAuth + mail send). Choose zero-retention / no-training API terms with the AI provider and list all sub-processors in your public policy.

## Compliance notes (not legal advice)
GDPR/UK-GDPR and similar laws will apply to EU/UK users: you need a lawful basis (contract + consent), a DPA with each sub-processor, a records-of-processing entry, breach procedures, a DPO/contact, and a cross-border transfer mechanism. CV data may include special-category information (e.g. photo, nationality); the app does not require or infer it. Automated decision-making: the app makes **no** decisions about the user; it ranks and drafts, and a human approves every send. The templates in `docs/legal/` must be reviewed by counsel.
Mailbox tracking is strictly opt-in. Only recipient-matched message metadata and a short classified snippet are retained. Incoming messages and follow-up drafts are included in the account export and removed by application-history/account deletion. OAuth credentials and message bodies are never included in exports.
