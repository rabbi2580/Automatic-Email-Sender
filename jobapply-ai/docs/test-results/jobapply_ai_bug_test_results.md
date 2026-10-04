# JobApply AI bug-test results

Source: `C:\Users\HP\Downloads\jobapply_ai_bug_tests.xlsx` (64 cases).

Run date: 2026-10-04

## Automated suite

```text
Command: cd backend && python -m pytest -q
Result: 162 passed, 1 skipped in 208.44s
```

The test fixture now forces `DEBUG=false`, so an unrelated shell value such as `DEBUG=release` cannot prevent test collection. The skipped test requires a running Redis instance.

Status meanings:

- `PASS`: covered by the existing automated suite or a static repository check and passed.
- `PARTIAL`: a related control is tested, but the exact workbook scenario still needs a dedicated test.
- `BLOCKED`: requires an unavailable external service, browser/device test, production configuration, or a fixture that is not present locally.

## Case results

| ID | Area | Result | Evidence / next action |
|---|---|---|---|
| S-01 | Setup | BLOCKED | Requires Docker and a clean Postgres volume. |
| S-02 | Setup | PASS | `backend/Dockerfile` runs `alembic upgrade head` before the API. |
| S-03 | Setup | PASS | 163 tests are collected and 37 SQLAlchemy tables are defined; README counts corrected. |
| S-04 | Setup | BLOCKED | SQLite passed; a Postgres run requires a live Postgres service. |
| S-05 | Setup | BLOCKED | Needs an isolated process with `AI_PROVIDER=openai_compatible` and no base URL. |
| S-06 | Setup | PASS | Frontend lint and production build passed. |
| S-07 | Setup | BLOCKED | Requires encrypted mailbox data created with an old key. |
| S-08 | Setup | BLOCKED | Requires two live Celery beat instances and a real scheduler window. |
| D-01 | Delivery | BLOCKED | Requires a concurrent slow SMTP mock and mid-send edit. |
| D-02 | Delivery | PASS | Duplicate-send protection is covered by `test_duplicate_send_protection`. |
| D-03 | Delivery | PASS | User-bound confirmation token covered by `test_token_bound_to_user`. |
| D-04 | Delivery | BLOCKED | Exact parallel cap race requires a concurrency test with a live delivery backend. |
| D-05 | Delivery | PASS | Permanent/transient delivery failure and quota behaviour are covered. |
| D-06 | Delivery | BLOCKED | Requires killing a worker after SMTP acceptance. |
| D-07 | Delivery | PASS | Unverified-email send paths are blocked. |
| D-08 | Delivery | BLOCKED | Exact boolean-fuzz matrix is not separately automated. |
| D-09 | Delivery | PASS | Editing after approval revokes approval and invalidates the token. |
| D-10 | Delivery | PASS | Header injection is neutralised by the input-safety tests. |
| D-11 | Delivery | BLOCKED | Requires malicious multi-recipient job fixtures and review workflow verification. |
| D-12 | Delivery | PASS | QC failures block approval/send. |
| D-13 | Delivery | PASS | Unapproved applications cannot be previewed or sent. |
| F-01 | Fabrication safety | PASS | Rewrite and grounding tests reject invented facts; Unicode bypass coverage is included in safety checks. |
| F-02 | Fabrication safety | PASS | Skill taxonomy and aliases are tested. |
| F-03 | Fabrication safety | PASS | Grounding uses boundaries so Java is not accepted from JavaScript. |
| F-04 | Fabrication safety | BLOCKED | Needs a dedicated multilingual/overlapping-date fixture matrix. |
| F-05 | Fabrication safety | PASS | Deterministic QC rejects fabricated skills, employers, and dates. |
| F-06 | Fabrication safety | PASS | Prompt-injection text is treated as untrusted content. |
| F-07 | Fabrication safety | BLOCKED | Requires the representative offline CV sample set. |
| T-01 | Tenant isolation | PASS | Tenant route isolation tests pass. |
| T-02 | Tenant isolation | BLOCKED | Requires a direct Celery task foreign-ID fixture. |
| T-03 | Tenant isolation | PASS | Signed URLs are user-bound, expire, and are invalid after deletion. |
| T-04 | Tenant isolation | PASS | List/aggregate leakage checks pass. |
| T-05 | Tenant isolation | BLOCKED | Needs an explicit mass-assignment payload matrix for every write schema. |
| T-06 | Tenant isolation | PASS | Refresh rotation, reuse detection, logout, and password-change revocation pass. |
| T-07 | Tenant isolation | PARTIAL | Generic auth errors pass; timing-equivalence measurement is not automated. |
| T-08 | Tenant isolation | PASS | Rate limiting is tested when enabled. |
| T-09 | Tenant isolation | PASS | Admin payloads do not expose private CV/application content. |
| T-10 | Tenant isolation | PASS | OAuth consent/state requirements are tested. |
| J-01 | Job intake | PASS | Private/loopback/metadata and unsupported schemes are blocked. |
| J-02 | Job intake | PASS | Redirects to private addresses are blocked. |
| J-03 | Job intake | PASS | Login-walled hosts are refused. |
| J-04 | Job intake | PASS | Robots and fetch failures are handled explicitly. |
| J-05 | Job intake | PASS | Response size/content-type and fetch safety limits are tested. |
| J-06 | Job intake | PASS | Script content is stripped before storage/display. |
| J-07 | Job intake | PASS | Duplicate jobs and tracking variants are covered. |
| U-01 | Upload | PASS | Upload validation rejects invalid file content/types. |
| U-02 | Upload | BLOCKED | Requires zip-bomb and 5,000-page sample fixtures. |
| U-03 | Upload | PASS | Storage keys reject traversal and remain tenant-scoped. |
| U-04 | Upload | BLOCKED | Requires scanned, Bangla, RTL, and multi-column CV sample files. |
| U-05 | Upload | BLOCKED | Malware scanning service/EICAR integration is not available in this local run. |
| P-01 | Privacy | PASS | Export excludes secrets and other users' data. |
| P-02 | Privacy | BLOCKED | Requires fault-injected S3 failure during account deletion. |
| P-03 | Privacy | BLOCKED | Requires production log/cache/Celery-result inspection after deletion. |
| P-04 | Privacy | PASS | AI-training is opt-in and logged. |
| P-05 | Privacy | BLOCKED | Requires production-mode verification-link logging check. |
| P-06 | Privacy | BLOCKED | Requires live beat polling after consent revocation. |
| M-01 | Matching | PASS | Empty/missing profile dimensions produce valid scores without division errors. |
| M-02 | Matching | PASS | AI cache behaviour and cost recording are covered. |
| M-03 | Matching | PASS | Invalid JSON, provider errors, retries, and heuristic fallback are covered. |
| M-04 | Matching | BLOCKED | Requires a load test and configured per-user cost-cap scenario. |
| FE-01 | Frontend | BLOCKED | Requires browser automation for rapid double-click interaction. |
| FE-02 | Frontend | BLOCKED | Requires browser/API interception to compare preview and token payload. |
| FE-03 | Frontend | BLOCKED | Requires a separate bad-runtime-environment production build. |
| FE-04 | Frontend | BLOCKED | Requires browser storage/security inspection; the known localStorage limitation is documented in `docs/SECURITY.md`. |

## Frontend verification

```text
cd frontend
npm run lint    # passed
npm run build   # passed
```

## Re-running the blocked cases

1. Start Docker Compose with a clean volume for S-01, S-04, S-08, and P-06.
2. Provide old-key mailbox fixtures, multilingual CV samples, EICAR, zip-bomb, and large-PDF fixtures for S-07, U-02, U-04, and U-05.
3. Add dedicated concurrency/worker-crash tests for D-01, D-04, D-06, and M-04.
4. Run Playwright against the frontend for FE-01 through FE-04.
5. Run production-like observability/privacy checks for P-02, P-03, and P-05.
