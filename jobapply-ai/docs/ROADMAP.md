# Roadmap

**MVP (this repository)** — auth; CV upload/parse/profile; job intake (text, URL, email text, image, PDF/DOCX; bulk); dedupe + deadlines; explainable configurable matching; tailored CV (PDF/DOCX/TEX), cover letter, email; QC; review/approve/confirm-send; Gmail/Outlook/SMTP; tracker + dashboard; limits/quotas; export/delete; admin metadata; Docker; tests; docs.

**Phase 2** — httpOnly-cookie sessions (BFF) + CSP; MFA; antivirus scanning; automated retention jobs; scheduled deadline/follow-up reminder emails; company enrichment with provenance (`job_post`/`public_source`/`ai_inference`); inbox reading for job intake (extra OAuth scopes + verification); job-board APIs/RSS; browser-assisted form filling for supported ATS (user present, never past CAPTCHA/login); Stripe billing wired to existing plan limits/usage records; Postgres RLS; key-rotation tooling; richer analytics; email open/reply tracking (opt-in).

**Phase 3** — interview preparation, skill-gap learning plans, salary insights, recommendations, team/career-coach workspaces, mobile app, additional UI languages.
