# 04 — API reference

Interactive docs: `GET /docs` (Swagger) and `/redoc`; machine-readable: `/openapi.json`. Base path `/api/v1`. All routes except `auth/*`, `files/{token}` and the OAuth callbacks require `Authorization: Bearer <access token>`. Foreign-tenant resources return **404**, never 403. Errors: `{"detail": string | [{msg,…}] | {code,message}}`.

Key flows: `POST /auth/register` → `POST /auth/login` → `POST /resumes/upload` → `POST /jobs/bulk` → `POST /jobs/analyze` → `POST /applications/generate` → `POST /applications/{id}/approve` → `POST /applications/send/preview` → `POST /applications/send` (`confirm: true` + `confirmation_token`).


## admin

| method | path | handler |
|---|---|---|
| GET | `/api/v1/admin/ai` | Ai Stats |
| GET | `/api/v1/admin/audit-log` | Audit Log |
| GET | `/api/v1/admin/delivery-failures` | Delivery Failures |
| GET | `/api/v1/admin/errors` | Errors |
| GET | `/api/v1/admin/feature-flags` | Flags |
| PUT | `/api/v1/admin/feature-flags` | Put Flag |
| GET | `/api/v1/admin/health` | Health |
| GET | `/api/v1/admin/integrations` | Integrations |
| GET | `/api/v1/admin/limits` | Limits |
| PUT | `/api/v1/admin/limits` | Put Limit |
| GET | `/api/v1/admin/usage` | Usage Overview |
| GET | `/api/v1/admin/users` | Users |
| PATCH | `/api/v1/admin/users/{user_id}` | Patch User |

## analytics

| method | path | handler |
|---|---|---|
| GET | `/api/v1/analytics` | Analytics |

## applications

| method | path | handler |
|---|---|---|
| GET | `/api/v1/applications` | List Applications |
| POST | `/api/v1/applications/approve-bulk` | Approve Bulk |
| POST | `/api/v1/applications/generate` | Generate |
| POST | `/api/v1/applications/send` | Send |
| POST | `/api/v1/applications/send/preview` | Send Preview |
| GET | `/api/v1/applications/{app_id}` | Get Application |
| PATCH | `/api/v1/applications/{app_id}` | Patch Application |
| POST | `/api/v1/applications/{app_id}/approve` | Approve |
| PATCH | `/api/v1/applications/{app_id}/cover-letter` | Edit Cover Letter |
| GET | `/api/v1/applications/{app_id}/documents/{doc_id}/url` | Document Url |
| PATCH | `/api/v1/applications/{app_id}/email` | Edit Email |
| POST | `/api/v1/applications/{app_id}/mark-applied` | Mark Applied |
| POST | `/api/v1/applications/{app_id}/qc` | Rerun Qc |
| POST | `/api/v1/applications/{app_id}/regenerate` | Regenerate |
| POST | `/api/v1/applications/{app_id}/reject` | Reject |

## auth

| method | path | handler |
|---|---|---|
| POST | `/api/v1/auth/change-password` | Change Password |
| GET | `/api/v1/auth/google/callback` | Google Callback |
| GET | `/api/v1/auth/google/login` | Google Login |
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/logout` | Logout |
| GET | `/api/v1/auth/me` | Me |
| PATCH | `/api/v1/auth/me` | Patch Me |
| POST | `/api/v1/auth/refresh` | Refresh |
| POST | `/api/v1/auth/register` | Register |
| POST | `/api/v1/auth/resend-verification` | Resend Verification |
| POST | `/api/v1/auth/verify-email` | Verify Email |

## files

| method | path | handler |
|---|---|---|
| GET | `/api/v1/files/{token}` | Download |

## integrations

| method | path | handler |
|---|---|---|
| GET | `/api/v1/integrations/email` | List Accounts |
| GET | `/api/v1/integrations/email/callback/{provider}` | Callback |
| POST | `/api/v1/integrations/email/connect` | Connect |
| POST | `/api/v1/integrations/email/smtp` | Connect Smtp |
| DELETE | `/api/v1/integrations/email/{account_id}` | Disconnect |
| POST | `/api/v1/integrations/email/{account_id}/default` | Make Default |

## jobs

| method | path | handler |
|---|---|---|
| POST | `/api/v1/jobs` | Add Job |
| GET | `/api/v1/jobs` | List Jobs |
| POST | `/api/v1/jobs/analyze` | Analyze |
| POST | `/api/v1/jobs/bulk` | Add Jobs Bulk |
| POST | `/api/v1/jobs/manual` | Manual Job |
| POST | `/api/v1/jobs/parse` | Parse Preview |
| POST | `/api/v1/jobs/upload` | Upload Jobs |
| GET | `/api/v1/jobs/{job_id}` | Get Job |
| PATCH | `/api/v1/jobs/{job_id}` | Patch Job |
| DELETE | `/api/v1/jobs/{job_id}` | Delete Job |
| POST | `/api/v1/jobs/{job_id}/not-duplicate` | Not Duplicate |
| POST | `/api/v1/jobs/{job_id}/retry` | Retry |

## matches

| method | path | handler |
|---|---|---|
| GET | `/api/v1/matches` | List Matches |
| POST | `/api/v1/matches/recompute` | Recompute |
| GET | `/api/v1/matches/{job_id}` | Get Match |

## notifications

| method | path | handler |
|---|---|---|
| GET | `/api/v1/notifications` | Notifications |

## privacy

| method | path | handler |
|---|---|---|
| DELETE | `/api/v1/privacy/account` | Delete Account |
| PUT | `/api/v1/privacy/ai-training` | Ai Training |
| DELETE | `/api/v1/privacy/application-history` | Delete History |
| GET | `/api/v1/privacy/audit-log` | My Audit Log |
| GET | `/api/v1/privacy/export` | Export Data |

## profile

| method | path | handler |
|---|---|---|
| GET | `/api/v1/profile` | Get Profile |
| PATCH | `/api/v1/profile` | Patch Profile |
| PUT | `/api/v1/profile/structured` | Replace Structured |

## resumes

| method | path | handler |
|---|---|---|
| GET | `/api/v1/resumes` | List Resumes |
| POST | `/api/v1/resumes/upload` | Upload Resume |
| GET | `/api/v1/resumes/versions` | List Versions |
| GET | `/api/v1/resumes/{resume_id}` | Get Resume |
| DELETE | `/api/v1/resumes/{resume_id}` | Delete Resume |
| GET | `/api/v1/resumes/{resume_id}/download` | Download Url |
| POST | `/api/v1/resumes/{resume_id}/reparse` | Reparse |

## settings

| method | path | handler |
|---|---|---|
| GET | `/api/v1/settings` | Get Settings Route |
| PUT | `/api/v1/settings` | Put Settings |

## usage

| method | path | handler |
|---|---|---|
| GET | `/api/v1/usage` | My Usage |
### Mailbox tracking and follow-ups

- `POST /integrations/email/connect` accepts `tracking: true` to request opt-in read-only tracking.
- `GET /applications/{id}/incoming` returns tenant-owned incoming metadata only.
- `POST /applications/{id}/undo-auto-update` reverses the latest automatic status change when it is still current.
- `GET|PUT /follow-ups/settings` manages wait days, maximum follow-ups, and stop-on-reply behavior.
- `POST /follow-ups/from-application/{id}` creates a grounded draft; `PATCH /follow-ups/{id}` edits it; `POST /follow-ups/{id}/approve` approves it; `POST /follow-ups/{id}/send/preview` and `/send` provide the final review/send gate.
