# 03 — Database schema

Generated from the SQLAlchemy models. Migrations: `backend/alembic/versions`. Tenant-owned tables carry an indexed `user_id` FK with `ON DELETE CASCADE` (log tables use `SET NULL` so aggregate metrics survive account deletion without keeping identity).


## `ai_cache`

| column | type | null | notes |
|---|---|---|---|
| key | VARCHAR | no | PK |
| task | VARCHAR | no |  |
| value | JSON/JSONB | no |  |
| created_at | DATETIME | no |  |

## `ai_request_logs`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | yes | FK → users.id (SET NULL), indexed |
| task | VARCHAR | no |  |
| provider | VARCHAR | no |  |
| model | VARCHAR | no |  |
| input_chars | INTEGER | no |  |
| output_chars | INTEGER | no |  |
| latency_ms | INTEGER | no |  |
| cache_hit | BOOLEAN | no |  |
| success | BOOLEAN | no |  |
| error | VARCHAR | yes |  |
| created_at | DATETIME | no | indexed |
| id | CHAR | no | PK |

Indexes: `ix_ai_logs_task_created` (task, created_at)

## `application_documents`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| application_id | CHAR | no | FK → applications.id (CASCADE), indexed |
| kind | VARCHAR | no |  |
| filename | VARCHAR | no |  |
| content_type | VARCHAR | no |  |
| storage_key | VARCHAR | no |  |
| size_bytes | INTEGER | no |  |
| sha256 | VARCHAR | no |  |
| resume_version_id | CHAR | yes | FK → resume_versions.id (SET NULL) |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `application_emails`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| application_id | CHAR | no | FK → applications.id (CASCADE), indexed |
| email_account_id | CHAR | yes | FK → email_accounts.id (SET NULL) |
| to_address | VARCHAR | no |  |
| subject | VARCHAR | no |  |
| body | TEXT | no |  |
| attachment_doc_ids | JSON/JSONB | no |  |
| status | VARCHAR | no |  |
| attempts | INTEGER | no |  |
| last_error | VARCHAR | yes |  |
| provider_message_id | VARCHAR | yes |  |
| idempotency_key | VARCHAR | yes | unique |
| sent_at | DATETIME | yes |  |
| edited_by_user | BOOLEAN | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `application_events`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| application_id | CHAR | no | FK → applications.id (CASCADE), indexed |
| type | VARCHAR | no |  |
| from_status | VARCHAR | yes |  |
| to_status | VARCHAR | yes |  |
| detail | JSON/JSONB | no |  |
| created_at | DATETIME | no |  |
| id | CHAR | no | PK |

## `applications`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| job_id | CHAR | no | FK → jobs.id (CASCADE), indexed |
| match_id | CHAR | yes | FK → job_matches.id (SET NULL) |
| status | VARCHAR | no | indexed |
| generation_status | VARCHAR | no |  |
| generation_reason | VARCHAR | yes |  |
| tone | VARCHAR | no |  |
| language | VARCHAR | no |  |
| qc_passed | BOOLEAN | no |  |
| qc_report | JSON/JSONB | no |  |
| approved_at | DATETIME | yes |  |
| sent_at | DATETIME | yes |  |
| channel | VARCHAR | no |  |
| notes | TEXT | no |  |
| reminder_at | DATETIME | yes |  |
| content_hash | VARCHAR | no |  |
| linkedin_message | TEXT | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |
| deleted_at | DATETIME | yes |  |

Indexes: `ix_app_user_status` (user_id, status)

## `audit_logs`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | yes | FK → users.id (SET NULL), indexed |
| action | VARCHAR | no | indexed |
| entity_type | VARCHAR | yes |  |
| entity_id | VARCHAR | yes |  |
| ip | VARCHAR | yes |  |
| meta | JSON/JSONB | no |  |
| created_at | DATETIME | no | indexed |
| id | CHAR | no | PK |

## `certifications`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| profile_id | CHAR | no | FK → profiles.id (CASCADE), indexed |
| name | VARCHAR | no |  |
| issuer | VARCHAR | no |  |
| date | VARCHAR | no |  |
| id | CHAR | no | PK |

## `companies`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| name | VARCHAR | no |  |
| normalized_name | VARCHAR | no | indexed |
| website | VARCHAR | no |  |
| description | TEXT | no |  |
| industry | VARCHAR | no |  |
| location | VARCHAR | no |  |
| size | VARCHAR | no |  |
| provenance | JSON/JSONB | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `cover_letters`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| application_id | CHAR | no | FK → applications.id (CASCADE), unique |
| tone | VARCHAR | no |  |
| language | VARCHAR | no |  |
| body | TEXT | no |  |
| grounding | JSON/JSONB | no |  |
| edited_by_user | BOOLEAN | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `education`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| profile_id | CHAR | no | FK → profiles.id (CASCADE), indexed |
| institution | VARCHAR | no |  |
| degree | VARCHAR | no |  |
| field | VARCHAR | no |  |
| level | VARCHAR | no |  |
| start_date | VARCHAR | no |  |
| end_date | VARCHAR | no |  |
| grade | VARCHAR | no |  |
| details | JSON/JSONB | no |  |
| sort_order | INTEGER | no |  |
| id | CHAR | no | PK |

## `email_accounts`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| provider | VARCHAR | no |  |
| address | VARCHAR | no |  |
| display_name | VARCHAR | no |  |
| encrypted_credentials | TEXT | no |  |
| scopes | JSON/JSONB | no |  |
| status | VARCHAR | no |  |
| consent_given_at | DATETIME | yes |  |
| last_used_at | DATETIME | yes |  |
| is_default | BOOLEAN | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |
| deleted_at | DATETIME | yes |  |

## `experience`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| profile_id | CHAR | no | FK → profiles.id (CASCADE), indexed |
| kind | VARCHAR | no |  |
| company | VARCHAR | no |  |
| title | VARCHAR | no |  |
| location | VARCHAR | no |  |
| start_date | VARCHAR | no |  |
| end_date | VARCHAR | no |  |
| is_current | BOOLEAN | no |  |
| bullets | JSON/JSONB | no |  |
| technologies | JSON/JSONB | no |  |
| sort_order | INTEGER | no |  |
| id | CHAR | no | PK |

## `feature_flags`

| column | type | null | notes |
|---|---|---|---|
| key | VARCHAR | no | unique |
| enabled | BOOLEAN | no |  |
| description | VARCHAR | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `integrations`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| kind | VARCHAR | no |  |
| status | VARCHAR | no |  |
| config | JSON/JSONB | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `job_matches`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| job_id | CHAR | no | FK → jobs.id (CASCADE), indexed |
| profile_id | CHAR | no | FK → profiles.id (CASCADE) |
| score | FLOAT | no |  |
| classification | VARCHAR | no |  |
| dimensions | JSON/JSONB | no |  |
| strong_matches | JSON/JSONB | no |  |
| partial_matches | JSON/JSONB | no |  |
| missing | JSON/JSONB | no |  |
| concerns | JSON/JSONB | no |  |
| explanation | TEXT | no |  |
| weights_used | JSON/JSONB | no |  |
| thresholds_used | JSON/JSONB | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `job_sources`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| batch_id | CHAR | yes | indexed |
| kind | VARCHAR | no |  |
| raw_text | TEXT | no |  |
| source_url | VARCHAR | no |  |
| file_key | VARCHAR | yes |  |
| filename | VARCHAR | yes |  |
| created_at | DATETIME | no |  |
| id | CHAR | no | PK |

## `jobs`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| source_id | CHAR | yes | FK → job_sources.id (SET NULL) |
| batch_id | CHAR | yes | indexed |
| company_id | CHAR | yes | FK → companies.id (SET NULL) |
| company_name | VARCHAR | no |  |
| job_title | VARCHAR | no |  |
| department | VARCHAR | no |  |
| location | VARCHAR | no |  |
| employment_type | VARCHAR | no |  |
| workplace_type | VARCHAR | no |  |
| salary | VARCHAR | no |  |
| experience_required | JSON/JSONB | no |  |
| education_required | JSON/JSONB | no |  |
| required_skills | JSON/JSONB | no |  |
| preferred_skills | JSON/JSONB | no |  |
| responsibilities | JSON/JSONB | no |  |
| benefits | JSON/JSONB | no |  |
| tech_stack | JSON/JSONB | no |  |
| deadline | DATE | yes | indexed |
| application_email | VARCHAR | no |  |
| application_url | VARCHAR | no |  |
| source | VARCHAR | no |  |
| source_url | VARCHAR | no |  |
| original_content | TEXT | no |  |
| extracted_information | JSON/JSONB | no |  |
| content_hash | VARCHAR | no | indexed |
| status | VARCHAR | no |  |
| status_reason | VARCHAR | yes |  |
| duplicate_of_id | CHAR | yes |  |
| duplicate_score | FLOAT | yes |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |
| deleted_at | DATETIME | yes |  |

Indexes: `ix_jobs_user_created` (user_id, created_at); `ix_jobs_user_deadline` (user_id, deadline)

## `notifications`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| kind | VARCHAR | no |  |
| title | VARCHAR | no |  |
| body | TEXT | no |  |
| entity_type | VARCHAR | yes |  |
| entity_id | VARCHAR | yes |  |
| due_at | DATETIME | yes |  |
| read_at | DATETIME | yes |  |
| created_at | DATETIME | no |  |
| id | CHAR | no | PK |

## `plan_limits`

| column | type | null | notes |
|---|---|---|---|
| plan | VARCHAR | no | indexed |
| metric | VARCHAR | no |  |
| period | VARCHAR | no |  |
| limit_value | INTEGER | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `profiles`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed, unique |
| full_name | VARCHAR | no |  |
| email | VARCHAR | no |  |
| phone | VARCHAR | no |  |
| location | VARCHAR | no |  |
| headline | VARCHAR | no |  |
| summary | TEXT | no |  |
| links | JSON/JSONB | no |  |
| years_experience | FLOAT | yes |  |
| target_roles | JSON/JSONB | no |  |
| preferred_locations | JSON/JSONB | no |  |
| work_preference | VARCHAR | no |  |
| salary_expectation | VARCHAR | no |  |
| work_authorization | VARCHAR | no |  |
| other_preferences | TEXT | no |  |
| languages | JSON/JSONB | no |  |
| achievements | JSON/JSONB | no |  |
| extracurriculars | JSON/JSONB | no |  |
| publications | JSON/JSONB | no |  |
| source_resume_id | CHAR | yes | FK → resumes.id (SET NULL) |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

Indexes: `ix_profiles_user_id` (user_id)

## `projects`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| profile_id | CHAR | no | FK → profiles.id (CASCADE), indexed |
| name | VARCHAR | no |  |
| description | TEXT | no |  |
| bullets | JSON/JSONB | no |  |
| technologies | JSON/JSONB | no |  |
| url | VARCHAR | no |  |
| kind | VARCHAR | no |  |
| sort_order | INTEGER | no |  |
| id | CHAR | no | PK |

## `refresh_tokens`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| token_hash | VARCHAR | no | indexed, unique |
| family_id | VARCHAR | no | indexed |
| expires_at | DATETIME | no |  |
| revoked_at | DATETIME | yes |  |
| created_at | DATETIME | no |  |
| id | CHAR | no | PK |

Indexes: `ix_refresh_tokens_token_hash` (token_hash)

## `resume_versions`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| resume_id | CHAR | yes | FK → resumes.id (SET NULL) |
| application_id | CHAR | yes | indexed |
| label | VARCHAR | no |  |
| role_type | VARCHAR | no |  |
| content | JSON/JSONB | no |  |
| template | VARCHAR | no |  |
| options | JSON/JSONB | no |  |
| pdf_key | VARCHAR | yes |  |
| docx_key | VARCHAR | yes |  |
| tex_key | VARCHAR | yes |  |
| content_hash | VARCHAR | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `resumes`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| filename | VARCHAR | no |  |
| content_type | VARCHAR | no |  |
| size_bytes | INTEGER | no |  |
| storage_key | VARCHAR | no |  |
| sha256 | VARCHAR | no | indexed |
| extracted_text | TEXT | no |  |
| status | VARCHAR | no |  |
| status_reason | VARCHAR | yes |  |
| is_master | BOOLEAN | no |  |
| label | VARCHAR | no |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |
| deleted_at | DATETIME | yes |  |

## `send_logs`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| application_id | CHAR | yes | indexed |
| provider | VARCHAR | no |  |
| recipient | VARCHAR | no |  |
| success | BOOLEAN | no |  |
| error | VARCHAR | yes |  |
| created_at | DATETIME | no | indexed |
| id | CHAR | no | PK |

## `skills`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| profile_id | CHAR | no | FK → profiles.id (CASCADE), indexed |
| name | VARCHAR | no |  |
| canonical | VARCHAR | no | indexed |
| category | VARCHAR | no |  |
| level | VARCHAR | yes |  |
| id | CHAR | no | PK |

## `subscriptions`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| plan | VARCHAR | no |  |
| status | VARCHAR | no |  |
| provider | VARCHAR | yes |  |
| provider_ref | VARCHAR | yes |  |
| current_period_end | DATETIME | yes |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |

## `usage_records`

| column | type | null | notes |
|---|---|---|---|
| user_id | CHAR | no | FK → users.id (CASCADE), indexed |
| metric | VARCHAR | no | indexed |
| quantity | INTEGER | no |  |
| input_tokens | INTEGER | no |  |
| output_tokens | INTEGER | no |  |
| est_cost_usd_micros | INTEGER | no |  |
| meta | JSON/JSONB | no |  |
| created_at | DATETIME | no | indexed |
| id | CHAR | no | PK |

## `users`

| column | type | null | notes |
|---|---|---|---|
| email | VARCHAR | no | indexed, unique |
| password_hash | VARCHAR | yes |  |
| google_sub | VARCHAR | yes | unique |
| full_name | VARCHAR | no |  |
| role | VARCHAR | no |  |
| email_verified | BOOLEAN | no |  |
| is_active | BOOLEAN | no |  |
| locale | VARCHAR | no |  |
| ai_training_opt_in | BOOLEAN | no |  |
| consent_terms_at | DATETIME | yes |  |
| consent_ai_disclosure_at | DATETIME | yes |  |
| flagged_reason | VARCHAR | yes |  |
| settings | JSON/JSONB | no |  |
| verification_token_hash | VARCHAR | yes |  |
| id | CHAR | no | PK |
| created_at | DATETIME | no |  |
| updated_at | DATETIME | no |  |
| deleted_at | DATETIME | yes |  |

Indexes: `ix_users_email` (email)
