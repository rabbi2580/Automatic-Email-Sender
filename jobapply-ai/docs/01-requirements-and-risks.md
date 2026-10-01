# 01 — Requirements Analysis, Ambiguities, Risks, MVP Scope

## 1. Product statement

**Upload your CV → add job posts → AI analyzes everything → review personalized applications → approve → send → track.**
AI-assisted, user-controlled, factually grounded, privacy-conscious, compliant with email/website restrictions. Multi-tenant SaaS, not a personal script.

## 2. Functional requirements (condensed from the spec)

| # | Area | Requirement |
|---|------|-------------|
| F1 | Auth | Email/password (Argon2id), Google OAuth, JWT access + rotating refresh tokens, RBAC (`user`, `admin`) |
| F2 | CV | Upload PDF/DOCX → text → structured **Candidate Profile**; original file preserved, never modified |
| F3 | Jobs | Intake: pasted text (one or many), URL, email text, image (OCR), PDF/DOCX. Bulk (20–30+). Normalised schema |
| F4 | Dedup | Company + title + URL + email + description similarity |
| F5 | Deadlines | Extract, show days remaining, sort by urgency, reminders |
| F6 | Company | Optional public-source enrichment; provenance of every field (`job_post` / `public_source` / `ai_inference`) |
| F7 | Matching | Multi-dimension weighted score, configurable weights and thresholds, fully explainable |
| F8 | Generation | Tailored CV (PDF/DOCX/LaTeX), cover letter (5 tones), email (subject/body), optional LinkedIn/HR message |
| F9 | QC | Automatic blocking checks before approval (fabrication, name/company/title mismatch, placeholders, recipient, attachments, duplicates) |
| F10 | Approval | Human-in-the-loop: per-application and bulk approve, explicit confirm-and-send dialog |
| F11 | Delivery | Gmail OAuth, Outlook OAuth, SMTP; modular channel interface; URL channel = assisted (open link), never bot-bypass |
| F12 | Tracking | 12-state pipeline, dashboard metrics, notes, reminders, event log |
| F13 | Privacy | Encryption at rest/in transit, signed download URLs, tenant isolation, audit logs, export, deletion |
| F14 | SaaS | Plans with configurable limits, usage records, quotas, abuse prevention |
| F15 | Ops | Structured logs, AI-request logs (no content), job-processing states, admin health panel |
| F16 | i18n | English + Bangla UI and generation language |

## 3. Non-functional requirements

* **Factual integrity** is a hard invariant, enforced in code (not by prompting alone).
* **No auto-send**: sending is impossible without an `approved` application, passing QC, and a signed confirmation token bound to the exact content previewed.
* **Cost**: cache + dedup + model routing + token caps + retry caps.
* **Portability**: provider abstraction for AI, storage, email. Runs fully offline with a deterministic *heuristic* provider (used in tests/dev and as a graceful fallback).
* **Testability**: every module is unit-testable without network.

## 4. Ambiguities and the decision taken

| Ambiguity | Decision |
|-----------|----------|
| "Open the application workflow and assist the user" for URL jobs | MVP: show link + prepared materials + copy buttons + "mark as applied manually". No headless form automation (Phase 2, opt-in per supported ATS, never past CAPTCHA/login walls). |
| Scraping a pasted job URL | Fetch with a polite, identified User-Agent, honour `robots.txt`, SSRF-guarded, no login-gated sites (LinkedIn/Facebook are refused with a message asking the user to paste the text). |
| "Connect Email" for job intake (read inbox) | MVP: user pastes email text. Inbox reading needs extra OAuth scopes + verification; Phase 2. Sending scope only in MVP (`gmail.send`, `Mail.Send`). |
| Company intelligence | Phase 2 module with the interface and provenance model in place; MVP stores only job-post-derived company data. |
| LaTeX export | Produces `.tex` source (no TeX engine bundled). PDF is produced by ReportLab, DOCX by python-docx. |
| LLM provider required? | No. Without keys the heuristic provider is used (lower quality extraction, still works). With keys, LLM agents are used and **validated against JSON schemas**; failures fall back to heuristics. |
| Free-text salary / currency | Stored as raw text plus best-effort numeric range; never used to reject. |
| Who sees admin data | Admin APIs return aggregates and metadata only; no endpoint exposes CV/job content to admins. |

## 5. Technical risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| LLM hallucination in CV/cover letter | Critical (user harm) | Deterministic CV assembly from the profile; LLM may only *select/reorder/reword* items by ID; QC verifies every skill/employer/degree/date against the profile; blocking failures |
| Prompt injection via job posts / CV | High | Untrusted text wrapped in delimiters, system rules forbid following embedded instructions, outputs schema-validated, no tool-use/side effects from LLM output, links in generated text stripped unless in profile |
| Spam / abuse of email sending | High | Per-user daily & hourly caps, per-recipient dedupe, confirmation tokens, plan limits, suspicious-activity flags, admin kill switch, verified-email requirement before sending |
| Credential theft (OAuth tokens/SMTP passwords) | High | Fernet (AES-128-CBC+HMAC) envelope encryption with key from env/KMS; least-privilege scopes; revocation on disconnect |
| Tenant data leakage | Critical | Single `get_owned()` access path; every table has `user_id`; automated tenant-isolation tests for every route |
| SSRF through URL intake | High | Block private/loopback/link-local ranges after DNS resolution, redirect re-validation, size/time caps |
| Malicious uploads | High | Content-type sniffing by magic bytes, size caps, no execution, parsed in worker, stored under random keys |
| OCR / parse failures | Medium | Explicit `failed` / `requires_review` states with reason + "Enter manually" path |
| LLM cost blow-up | Medium | Content-hash cache, dedupe before AI, cheap model for extraction, per-request token caps, batch endpoint, usage records |
| Provider lock-in | Medium | `AIProvider` interface; OpenAI/Anthropic/Gemini/OpenAI-compatible (local) adapters |
| Legal / ToS | Medium | Consent to send, AI disclosure, no automation past anti-bot controls, ToS + Privacy Policy templates (to be reviewed by counsel) |
| ATS parsing of generated CV | Medium | Single-column, standard headings, real text (no images/tables), tested by round-trip text extraction |

## 6. MVP scope (this repository)

In: authentication; CV upload + parsing + profile; job intake by text/URL/image/PDF/DOCX; bulk processing; matching with explainability and configurable weights/thresholds; tailored CV (PDF/DOCX/TEX) / cover letter / email; QC; human review + bulk approve + confirm-and-send; Gmail/Outlook/SMTP delivery; tracker + dashboard; duplicate + deadline detection; rate limits, quotas, audit logs; data export/deletion; Docker; docs; tests.

Deferred (Phase 2/3): company web enrichment, job-board APIs, inbox reading, browser-assisted forms, subscriptions billing (limits and usage records exist), advanced analytics, interview prep, recommendations.
