"""Orchestration of the processing pipelines. Each function is idempotent, takes ids, and records an explicit status.

resume:      Original CV → text → CV Extraction Agent → grounded → Candidate Profile
job:         raw text → Job Extraction Agent → grounded → dedupe → company → match
application: Tailoring → CV exports → Cover Letter → Email → Quality Control → awaiting_review
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Application, ApplicationDocument, ApplicationEmail, Certification, Company, CoverLetter, Education, EmailAccount, Experience, Job, JobMatch,
    JobSource, Notification, Profile, Project, Resume, ResumeVersion, Skill, User,
)
from app.models.base import utcnow
from app.schemas.ai import JobExtraction, ProfileExtraction, TailorSelection
from app.services.ai.safety import wrap_untrusted
from app.services.ai.service import AIService
from app.services.dedupe import content_hash, find_duplicate_for_user, norm_company
from app.services.generation import exporters
from app.services.generation.cv_builder import BuildOptions, ROLE_LABELS, build_tailored_cv, classify_role_type
from app.services.generation.letters import analyze_fit, generate_cover_letter, generate_email
from app.services.matching.engine import compute_match
from app.services.parsing.cv_parser import parse_cv_text
from app.services.parsing.documents import DocumentError, extract_text
from app.services.parsing.job_parser import parse_job_text
from app.services.parsing.skills import canonicalize, category_of, find_skills
from app.services.profile_view import candidate_view, job_snapshot, job_view, profile_snapshot
from app.services.qc import run_qc
from app.services.storage import get_storage, new_key
from app.services.user_settings import get_user_settings
from app.services.workflow import transition

log = logging.getLogger("jobapply.pipeline")


# ======================================================================= resume ==================================================

def _in_text(needle: str, hay_lower: str) -> bool:
    n = re.sub(r"\s+", " ", needle.lower()).strip()
    if not n:
        return False
    if n in hay_lower:
        return True
    words = [w for w in re.findall(r"[a-z0-9]+", n) if len(w) > 2]
    return bool(words) and all(w in hay_lower for w in words[:3])


def ground_extraction(ext: ProfileExtraction, text: str) -> ProfileExtraction:
    """Drop anything an extractor produced that cannot be found in the source CV text (anti-hallucination)."""
    hay = re.sub(r"\s+", " ", text.lower())
    ext.experiences = [e for e in ext.experiences if _in_text(e.company, hay) or _in_text(e.title, hay)]
    ext.educations = [e for e in ext.educations if _in_text(e.institution, hay) or _in_text(e.degree, hay)]
    ext.projects = [p for p in ext.projects if _in_text(p.name, hay)]
    ext.certifications = [c for c in ext.certifications if _in_text(c.name, hay)]
    ext.skills = [s for s in ext.skills if _in_text(s.name, hay) or canonicalize(s.name).lower() in hay or any(a in hay for a in [s.name.lower()])]
    for e in ext.experiences:
        e.bullets = [b for b in e.bullets if _in_text(b[:60], hay)]
    for p in ext.projects:
        p.bullets = [b for b in p.bullets if _in_text(b[:60], hay)]
    if ext.email and ext.email.lower() not in hay:
        ext.email = ""
    if ext.phone and re.sub(r"\D", "", ext.phone) not in re.sub(r"\D", "", text):
        ext.phone = ""
    ext.full_name = ext.full_name if _in_text(ext.full_name, hay) else ""
    return ext


def apply_extraction(db: Session, user: User, ext: ProfileExtraction, resume: Resume | None, overwrite_scalars: bool = False) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if not profile:
        profile = Profile(user_id=user.id)
        db.add(profile)
        db.flush()
    # scalars: user-entered values win unless overwrite requested
    for attr in ("full_name", "email", "phone", "location", "headline", "summary"):
        val = getattr(ext, attr)
        if val and (overwrite_scalars or not getattr(profile, attr)):
            setattr(profile, attr, val)
    if not profile.email:
        profile.email = user.email
    links = dict(profile.links or {})
    for k, v in ext.links.items():
        if k not in links or not links[k]:
            links[k] = v
    profile.links = links
    if ext.years_experience is not None and (overwrite_scalars or profile.years_experience is None):
        profile.years_experience = ext.years_experience
    profile.languages = ext.languages or profile.languages
    profile.achievements, profile.publications, profile.extracurriculars = ext.achievements, ext.publications, ext.extracurriculars
    if resume:
        profile.source_resume_id = resume.id

    for model in (Skill, Experience, Education, Project, Certification):
        db.execute(delete(model).where(model.profile_id == profile.id))
    seen = set()
    for s in ext.skills:
        canon = canonicalize(s.name)
        if canon.lower() in seen:
            continue
        seen.add(canon.lower())
        db.add(Skill(user_id=user.id, profile_id=profile.id, name=canon, canonical=canon, category=s.category if s.category != "technical" else category_of(canon)))
    for i, e in enumerate(ext.experiences):
        db.add(Experience(user_id=user.id, profile_id=profile.id, sort_order=i, **e.model_dump()))
    for i, e in enumerate(ext.educations):
        db.add(Education(user_id=user.id, profile_id=profile.id, sort_order=i, **e.model_dump()))
    for i, p in enumerate(ext.projects):
        db.add(Project(user_id=user.id, profile_id=profile.id, sort_order=i, **p.model_dump()))
    for c in ext.certifications:
        db.add(Certification(user_id=user.id, profile_id=profile.id, **c.model_dump()))
    db.flush()
    db.refresh(profile)
    return profile


def process_resume(db: Session, resume_id: uuid.UUID) -> Resume:
    resume = db.get(Resume, resume_id)
    if not resume:
        raise LookupError("resume not found")
    user = db.get(User, resume.user_id)
    resume.status, resume.status_reason = "processing", None
    db.commit()
    try:
        data = get_storage().get(resume.storage_key)
        doc = extract_text(data, resume.filename)
    except DocumentError as e:
        resume.status, resume.status_reason = "failed", e.reason
        db.commit()
        return resume
    except Exception as e:  # noqa: BLE001
        log.exception("resume read failed")
        resume.status, resume.status_reason = "failed", f"Could not read the stored file ({type(e).__name__})."
        db.commit()
        return resume
    resume.extracted_text = doc.text
    ai = AIService(db, user.id)
    ext, source = ai.structured(
        task="cv_extract", schema=ProfileExtraction, tier="cheap",
        user_prompt="Extract the candidate profile from this CV text. Copy facts exactly; keep dates as written.\n" + wrap_untrusted("cv", doc.text, ai.settings.ai_max_input_chars),
        fallback=lambda: parse_cv_text(doc.text),
    )
    ext = ground_extraction(ext, doc.text)
    if source == "llm" and not (ext.experiences or ext.educations or ext.projects):  # LLM output was entirely ungrounded → heuristic
        ext = ground_extraction(parse_cv_text(doc.text), doc.text)
    profile = apply_extraction(db, user, ext, resume)
    thin = not profile.full_name or not (ext.experiences or ext.educations or ext.projects)
    resume.status = "requires_review" if thin else "completed"
    resume.status_reason = ("We could not confidently read your name or any experience, education or projects. Please review and complete your profile."
                            if thin else (f"Read with OCR." if doc.used_ocr else None))
    db.commit()
    return resume


# ======================================================================= job =====================================================

def _ground_job(ext: JobExtraction, text: str) -> JobExtraction:
    hay = re.sub(r"\s+", " ", text.lower())
    if ext.company and not _in_text(ext.company, hay):
        ext.warnings.append(f"Company '{ext.company}' was not found verbatim in the post and was removed.")
        ext.company = ""
    if ext.application_email and ext.application_email.lower() not in hay:
        ext.application_email = ""
    if ext.application_url and ext.application_url.lower().rstrip("/") not in hay:
        ext.application_url = ""
    known = lambda skills: [s for s in (canonicalize(x) for x in skills) if s.lower() in hay or _in_text(s, hay)]  # noqa: E731
    ext.required_skills, ext.preferred_skills, ext.tech_stack = known(ext.required_skills), known(ext.preferred_skills), known(ext.tech_stack)
    return ext


def apply_job_extraction(db: Session, job: Job, ext: JobExtraction, source_label: str) -> None:
    job.company_name, job.job_title, job.department = ext.company, ext.job_title, ext.department
    job.location, job.employment_type, job.workplace_type, job.salary = ext.location, ext.employment_type, ext.workplace_type, ext.salary
    job.experience_required = {"min_years": ext.min_years, "max_years": ext.max_years, "text": ext.experience_text}
    job.education_required = {"level": ext.education_level, "fields": ext.education_fields, "text": ext.education_text}
    job.required_skills, job.preferred_skills, job.tech_stack = ext.required_skills, ext.preferred_skills, ext.tech_stack
    job.responsibilities, job.benefits, job.deadline = ext.responsibilities, ext.benefits, ext.deadline
    job.application_email, job.application_url = ext.application_email, ext.application_url
    job.extracted_information = {"warnings": ext.warnings, "extraction": source_label,
                                 "provenance": {"company": "job_post", "title": "job_post", "details": "job_post"}}


def get_or_create_company(db: Session, user_id: uuid.UUID, name: str) -> Company | None:
    if not name:
        return None
    norm = norm_company(name)
    c = db.scalar(select(Company).where(Company.user_id == user_id, Company.normalized_name == norm))
    if not c:
        c = Company(user_id=user_id, name=name, normalized_name=norm, provenance={"name": {"value": name, "source": "job_post"}})
        db.add(c)
        db.flush()
    return c


def process_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise LookupError("job not found")
    user = db.get(User, job.user_id)
    job.status, job.status_reason = "processing", None
    db.commit()
    text = job.original_content
    ai = AIService(db, user.id)
    ext, source = ai.structured(
        task="job_extract", schema=JobExtraction, tier="cheap",
        user_prompt="Extract this job posting into the schema. Leave unknown fields empty. deadline must be ISO date (YYYY-MM-DD) only if stated.\n"
                    f"Today's date is {date.today().isoformat()}.\n" + wrap_untrusted("job_post", text, ai.settings.ai_max_input_chars),
        fallback=lambda: parse_job_text(text, source_url=job.source_url),
    )
    ext = _ground_job(ext, text)
    if source == "llm":  # fill gaps the model missed with deterministic parsing
        base = parse_job_text(text, source_url=job.source_url)
        for f in ("job_title", "company", "application_email", "location", "salary"):
            if not getattr(ext, f) and getattr(base, f):
                setattr(ext, f, getattr(base, f))
        ext.deadline = ext.deadline or base.deadline
    apply_job_extraction(db, job, ext, source)
    job.content_hash = content_hash(text)
    c = get_or_create_company(db, user.id, job.company_name)
    job.company_id = c.id if c else None

    dup = find_duplicate_for_user(db, user.id, {
        "id": job.id, "company_name": job.company_name, "job_title": job.job_title, "application_email": job.application_email,
        "application_url": job.application_url, "source_url": job.source_url, "original_content": text, "content_hash": job.content_hash})
    if dup:
        job.duplicate_of_id, job.duplicate_score = dup.job_id, dup.score
        job.extracted_information = {**job.extracted_information, "duplicate_reasons": dup.reasons}
    else:
        job.duplicate_of_id = job.duplicate_score = None

    if not ext.is_job_posting:
        job.status, job.status_reason = "requires_review", "This text does not look like a job posting. Check it or enter the details manually."
    elif not job.job_title and not job.company_name:
        job.status, job.status_reason = "requires_review", "We could not find a job title or a company. Please enter them manually."
    else:
        job.status = "completed"
        job.status_reason = "; ".join(ext.warnings[:2]) or None
    db.commit()
    if job.status in ("completed", "requires_review") and job.job_title:
        match_job(db, user, job)
    if job.deadline:
        _ensure_deadline_reminder(db, user, job)
    db.commit()
    return job


def _ensure_deadline_reminder(db: Session, user: User, job: Job) -> None:
    from datetime import datetime, time, timedelta, timezone

    days = int(get_user_settings(user).get("reminder_days_before_deadline", 3))
    existing = db.scalar(select(Notification).where(Notification.user_id == user.id, Notification.entity_id == str(job.id), Notification.kind == "deadline"))
    due = datetime.combine(job.deadline - timedelta(days=days), time(8, 0), tzinfo=timezone.utc)
    if existing:
        existing.due_at = due
    else:
        db.add(Notification(user_id=user.id, kind="deadline", title=f"Deadline approaching: {job.job_title or 'job'}",
                            body=f"{job.company_name or 'Unknown company'} — apply by {job.deadline.isoformat()}", entity_type="job", entity_id=str(job.id), due_at=due))


def match_job(db: Session, user: User, job: Job) -> JobMatch | None:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if not profile:
        return None
    s = get_user_settings(user)
    res = compute_match(candidate_view(profile_snapshot(profile)), job_view(job_snapshot(job)), s["weights"], s["thresholds"])
    m = db.scalar(select(JobMatch).where(JobMatch.job_id == job.id, JobMatch.profile_id == profile.id))
    if not m:
        m = JobMatch(user_id=user.id, job_id=job.id, profile_id=profile.id, score=0, classification="weak")
        db.add(m)
    for k in ("score", "classification", "dimensions", "strong_matches", "partial_matches", "missing", "concerns", "explanation", "weights_used", "thresholds_used"):
        setattr(m, k, res[k])
    db.flush()
    return m


# ======================================================================= application =============================================

def _doc_dict(d: ApplicationDocument) -> dict:
    return {"id": str(d.id), "kind": d.kind, "filename": d.filename, "sha256": d.sha256}


def _save_doc(db: Session, user_id: uuid.UUID, app_id: uuid.UUID, kind: str, filename: str, ctype: str, data: bytes, rv_id=None) -> ApplicationDocument:
    ext = filename.rsplit(".", 1)[-1]
    key = new_key(user_id, "docs", ext)
    get_storage().put(key, data, ctype)
    d = ApplicationDocument(user_id=user_id, application_id=app_id, kind=kind, filename=filename, content_type=ctype, storage_key=key,
                            size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), resume_version_id=rv_id)
    db.add(d)
    db.flush()
    return d


def _safe_name(*parts: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", "_".join(p for p in parts if p)).strip("_")[:80]


def email_content_hash(to: str, subject: str, body: str, docs: list[dict]) -> str:
    return hashlib.sha256(json.dumps({"to": to.lower().strip(), "s": subject, "b": body, "d": sorted(d["sha256"] for d in docs)}, sort_keys=True).encode()).hexdigest()


def letter_to_text(letter: dict) -> str:
    return "\n\n".join([letter["greeting"], *letter["paragraphs"], letter["closing"]]).strip()


def text_to_letter(text: str) -> dict:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(parts) < 3:
        return {"greeting": parts[0] if parts else "", "paragraphs": parts[1:], "closing": ""}
    closing_idx = len(parts) - 1
    if len(parts) >= 4 and len(parts[-1]) < 60 and "\n" not in parts[-1]:  # signature as its own block
        closing_idx = len(parts) - 2
        closing = parts[-2] + "\n\n" + parts[-1]
        return {"greeting": parts[0], "paragraphs": parts[1:closing_idx], "closing": closing}
    return {"greeting": parts[0], "paragraphs": parts[1:closing_idx], "closing": parts[closing_idx]}


def _tailor_selection(ai: AIService, profile: dict, job: dict) -> TailorSelection | None:
    if not ai.llm_enabled:
        return None
    facts = {"skills": [{"id": s["id"], "name": s["name"]} for s in profile["skills"]],
             "projects": [{"id": p["id"], "name": p["name"], "bullets": p["bullets"]} for p in profile["projects"]],
             "experience": [{"id": e["id"], "title": e["title"], "bullets": e["bullets"]} for e in profile["experiences"]]}
    prompt = ("Reorder this candidate's skills/projects so the most relevant to the job come first, and optionally write a 2-sentence summary using ONLY these facts. "
              "Return ids from the lists only. bullet_rewrites may reword a bullet for clarity but must not add skills, numbers or claims.\n"
              f"Facts: {json.dumps(facts, ensure_ascii=False)}\nJob:\n" +
              wrap_untrusted("job", f"{job['job_title']} at {job['company_name']}. Required: {', '.join(job['required_skills'])}. Responsibilities: {'; '.join(job['responsibilities'][:6])}", 3000))
    try:
        sel, _ = ai.structured(task="cv_tailor", user_prompt=prompt, schema=TailorSelection, tier="strong", fallback=lambda: TailorSelection())
        return sel
    except Exception:  # noqa: BLE001
        return None


def generate_application(db: Session, user: User, job_id: uuid.UUID, *, tone: str | None = None, language: str | None = None,
                         options: dict | None = None) -> Application:
    """Create (or regenerate) the full application package for a job and run QC."""
    job = db.get(Job, job_id)
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if not job or job.user_id != user.id:
        raise LookupError("job not found")
    if not profile or not (profile.skills or profile.experiences or profile.educations or profile.projects):
        raise ValueError("Upload and parse a CV (or complete your profile) before generating applications.")
    cfg = get_user_settings(user)
    o = {**{"template": cfg["cv_template"], "font": cfg["cv_font"], "pages": cfg["cv_pages"], "style": cfg["cv_style"]}, **(options or {})}
    tone = tone or cfg["tone"]
    language = language or cfg["language"]
    include_letter = bool(o.get("include_cover_letter", cfg["include_cover_letter"]))

    app = db.scalar(select(Application).where(Application.user_id == user.id, Application.job_id == job.id))
    if app and app.status in ("sent", "application_confirmed", "interview", "offer", "rejected"):
        raise ValueError("This application has already been sent; it cannot be regenerated.")
    if not app:
        app = Application(user_id=user.id, job_id=job.id, status="saved")
        db.add(app)
        db.flush()
    m = db.scalar(select(JobMatch).where(JobMatch.job_id == job.id)) or match_job(db, user, job)
    app.match_id = m.id if m else None
    app.tone, app.language, app.generation_status, app.generation_reason = tone, language, "processing", None
    transition(db, app, "analyzing")
    db.commit()

    ai = AIService(db, user.id)
    psnap, jsnap = profile_snapshot(profile), job_snapshot(job)
    try:
        sel = _tailor_selection(ai, psnap, jsnap)
        bopts = BuildOptions(template=o["template"], font=o["font"], pages=int(o["pages"]), style=o["style"], language=language)
        cv = build_tailored_cv(psnap, jsnap, bopts, sel)
        render_opts = {"template": bopts.template, "font": bopts.font, "pages": bopts.pages, "language": language}
        try:
            pdf, pages, cv_final = exporters.render_pdf(cv, render_opts)
        except exporters.ComplexScriptUnavailable:  # server lacks Pango/WeasyPrint: fall back to Latin headings for the PDF
            render_opts = {**render_opts, "language": "en"}
            pdf, pages, cv_final = exporters.render_pdf(cv, render_opts)
        docx_bytes = exporters.render_docx(cv_final, render_opts)
        tex = exporters.render_tex(cv_final, render_opts)
        letter, lsrc, lproblems = generate_cover_letter(ai, psnap, jsnap, tone, language)
        fit = analyze_fit(psnap, jsnap)
        email = generate_email(psnap, jsnap, tone, language, include_letter, fit["matched"])
    except Exception as exc:  # noqa: BLE001
        log.exception("application generation failed")
        app.generation_status, app.generation_reason = "failed", f"Generation failed ({type(exc).__name__}). Try again."
        db.commit()
        return app

    # remove previous generated artefacts for regeneration
    for d in db.scalars(select(ApplicationDocument).where(ApplicationDocument.application_id == app.id)):
        get_storage().delete(d.storage_key)
        db.delete(d)
    for rv in db.scalars(select(ResumeVersion).where(ResumeVersion.application_id == app.id)):
        db.delete(rv)
    db.flush()

    role_type = cv_final["meta"]["role_type"]
    base = _safe_name(psnap["full_name"], "CV", job.company_name)
    rv = ResumeVersion(user_id=user.id, resume_id=profile.source_resume_id, application_id=app.id, label=ROLE_LABELS.get(role_type, "CV"), role_type=role_type,
                       content=cv_final, template=bopts.template, options=render_opts, content_hash=hashlib.sha256(json.dumps(cv_final, sort_keys=True).encode()).hexdigest())
    db.add(rv)
    db.flush()
    docs = [
        _save_doc(db, user.id, app.id, "cv_pdf", base + ".pdf", "application/pdf", pdf, rv.id),
        _save_doc(db, user.id, app.id, "cv_docx", base + ".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx_bytes, rv.id),
        _save_doc(db, user.id, app.id, "cv_tex", base + ".tex", "application/x-tex", tex.encode(), rv.id),
    ]
    cl_row = db.scalar(select(CoverLetter).where(CoverLetter.application_id == app.id))
    if not cl_row:
        cl_row = CoverLetter(user_id=user.id, application_id=app.id)
        db.add(cl_row)
    cl_row.tone, cl_row.language, cl_row.body, cl_row.edited_by_user = tone, language, letter_to_text(letter), False
    cl_row.grounding = {"entity_ids": letter.get("referenced_entity_ids", []), "source": lsrc, "rejected_llm_problems": lproblems}
    letter_pdf_ok = True
    if include_letter:
        lbase = _safe_name(psnap["full_name"], "Cover_Letter", job.company_name)
        header = {"name": psnap["full_name"], "email": psnap["email"], "phone": psnap["phone"], "location": psnap["location"]}
        try:
            docs.append(_save_doc(db, user.id, app.id, "cover_letter_pdf", lbase + ".pdf", "application/pdf",
                                  exporters.render_cover_letter_pdf(letter, header, {**render_opts, "language": language})))
        except exporters.ComplexScriptUnavailable:
            letter_pdf_ok = False  # Bangla letter without a shaping engine: attach the DOCX instead
        docs.append(_save_doc(db, user.id, app.id, "cover_letter_docx", lbase + ".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                              exporters.render_cover_letter_docx(letter, header)))
    attach = [d for d in docs if d.kind == "cv_pdf" or d.kind == ("cover_letter_pdf" if letter_pdf_ok else "cover_letter_docx")]

    acct = db.scalar(select(EmailAccount).where(EmailAccount.user_id == user.id, EmailAccount.deleted_at.is_(None), EmailAccount.status == "active").order_by(EmailAccount.is_default.desc()))
    em = db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == app.id))
    if not em:
        em = ApplicationEmail(user_id=user.id, application_id=app.id)
        db.add(em)
    em.to_address, em.subject, em.body = job.application_email, email["subject"], email["body"]
    em.attachment_doc_ids = [str(d.id) for d in attach]
    em.email_account_id = acct.id if acct else None
    em.status, em.edited_by_user, em.idempotency_key = "draft", False, None
    app.linkedin_message = email["linkedin_message"]
    app.channel = "email" if job.application_email else ("url_assisted" if job.application_url else "")
    app.generation_status = "completed"
    transition(db, app, "cv_generated")
    db.flush()
    run_application_qc(db, app, pdf=pdf, pages=pages, commit=False)
    transition(db, app, "awaiting_review")
    app.approved_at = None
    db.commit()
    return app


def run_application_qc(db: Session, app: Application, *, pdf: bytes | None = None, pages: int | None = None, commit: bool = True) -> dict:
    job = db.get(Job, app.job_id)
    profile = db.scalar(select(Profile).where(Profile.user_id == app.user_id))
    rv = db.scalar(select(ResumeVersion).where(ResumeVersion.application_id == app.id))
    cl = db.scalar(select(CoverLetter).where(CoverLetter.application_id == app.id))
    em = db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == app.id))
    docs = list(db.scalars(select(ApplicationDocument).where(ApplicationDocument.application_id == app.id)))
    if pdf is None:
        cvdoc = next((d for d in docs if d.kind == "cv_pdf"), None)
        if cvdoc:
            pdf = get_storage().get(cvdoc.storage_key)
            from pypdf import PdfReader
            import io
            pages = len(PdfReader(io.BytesIO(pdf)).pages)
    attached = [d for d in docs if str(d.id) in (em.attachment_doc_ids or [])]
    sent = db.execute(select(ApplicationEmail.to_address, Job.job_title).join(Application, Application.id == ApplicationEmail.application_id)
                      .join(Job, Job.id == Application.job_id).where(ApplicationEmail.user_id == app.user_id, ApplicationEmail.status == "sent",
                                                                       ApplicationEmail.application_id != app.id)).all()
    letter = text_to_letter(cl.body)
    include_letter = any(d.kind.startswith("cover_letter") for d in attached)
    report = run_qc(profile=profile_snapshot(profile), job=job_snapshot(job), cv=rv.content, pdf=pdf, pages=pages, pages_limit=int(rv.options.get("pages", 1)),
                    letter=letter, email={"to_address": em.to_address, "subject": em.subject, "body": em.body},
                    attachments=[_doc_dict(d) for d in attached], include_letter=include_letter, prior_sends=[{"to": r[0], "job_title": r[1]} for r in sent])
    app.qc_report, app.qc_passed = report, report["passed"]
    if not report["passed"] and app.status == "approved":
        transition(db, app, "awaiting_review", detail={"reason": "qc_failed_after_edit"})
        app.approved_at = None
    if commit:
        db.commit()
    return report
