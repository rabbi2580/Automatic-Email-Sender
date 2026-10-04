from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.helpers import job_out
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user, get_owned
from app.core.ratelimit import rate_limit
from app.models import Application, Job, JobMatch, JobSource, User
from app.models.base import utcnow
from app.schemas.api import JobAnalyzeIn, JobBulkIn, JobPatch, JobTextIn
from app.services import pipeline, usage
from app.services.audit import audit
from app.services.parsing.documents import DocumentError, extract_text, sniff_kind
from app.services.parsing.job_parser import parse_job_text, split_multiple_jobs
from app.services.cv_quality import ats_score
from app.models import Profile
from app.services.parsing.skills import canonicalize
from app.services.parsing.url_fetch import FetchError, fetch_job_page
from app.services.storage import get_storage, new_key
from app.workers.dispatch import enqueue

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _new_job(db: Session, user: User, batch: uuid.UUID, kind: str, text: str, url: str = "", file_key: str | None = None, filename: str | None = None,
             fail_reason: str | None = None) -> Job:
    src = JobSource(user_id=user.id, batch_id=batch, kind=kind, raw_text=text, source_url=url, file_key=file_key, filename=filename)
    db.add(src)
    db.flush()
    job = Job(user_id=user.id, source_id=src.id, batch_id=batch, original_content=text, source=kind, source_url=url,
              status="failed" if fail_reason else "queued", status_reason=fail_reason)
    db.add(job)
    db.flush()
    return job


def _reserve(db: Session, user: User, n: int) -> None:
    s = get_settings()
    if n > s.max_bulk_jobs:
        raise HTTPException(413, f"You can add at most {s.max_bulk_jobs} jobs at once.")
    usage.check_quota(db, user, "job_analyses", n)


def _intake(db: Session, user: User, items: list[JobTextIn]) -> dict:
    batch = uuid.uuid4()
    # expand pasted blobs first so quota/bulk limits are exact
    expanded: list[tuple[str, str, str]] = []  # (kind, text, url)
    for it in items:
        if it.kind == "url":
            if not it.url:
                raise HTTPException(422, "A URL is required for kind 'url'.")
            expanded.append(("url", "", it.url))
        else:
            if not it.text or len(it.text.strip()) < 20:
                raise HTTPException(422, "Paste the job text (at least a few lines).")
            parts = split_multiple_jobs(it.text) if it.split else [it.text.strip()]
            expanded += [(it.kind, p, "") for p in parts]
    _reserve(db, user, len(expanded))
    jobs: list[Job] = []
    for kind, text, url in expanded:
        if kind == "url":
            try:
                page_text, final_url = fetch_job_page(url)
                jobs.append(_new_job(db, user, batch, "url", page_text, final_url))
            except FetchError as e:
                jobs.append(_new_job(db, user, batch, "url", "", url, fail_reason=e.reason))
        else:
            jobs.append(_new_job(db, user, batch, kind, text))
        usage.record_usage(db, user.id, "job_analyses", 1)
    audit(db, user.id, "jobs.intake", entity_type="job_batch", entity_id=batch, count=len(jobs))
    db.commit()
    for j in jobs:
        if j.status == "queued":
            enqueue("process_job", str(j.id))
    return _batch_response(db, user, batch)


def _batch_response(db: Session, user: User, batch: uuid.UUID) -> dict:
    db.expire_all()
    rows = db.execute(select(Job, JobMatch).outerjoin(JobMatch, JobMatch.job_id == Job.id).where(Job.user_id == user.id, Job.batch_id == batch).order_by(Job.created_at)).all()
    return {"batch_id": str(batch), "jobs": [job_out(j, m) for j, m in rows], "summary": _summary([(j, m) for j, m in rows])}


def _summary(rows: list[tuple[Job, JobMatch | None]]) -> dict:
    s = {"total": len(rows), "processed": 0, "strong": 0, "potential": 0, "weak": 0, "not_suitable": 0, "failed": 0, "requires_review": 0, "queued": 0, "duplicates": 0}
    for j, m in rows:
        if j.status == "failed":
            s["failed"] += 1
        elif j.status == "requires_review":
            s["requires_review"] += 1
        elif j.status in ("queued", "processing"):
            s["queued"] += 1
        if j.status in ("completed", "requires_review"):
            s["processed"] += 1
        if j.duplicate_of_id:
            s["duplicates"] += 1
        if m and j.status in ("completed", "requires_review") and not j.duplicate_of_id:
            s[m.classification] += 1
    return s


@router.post("", status_code=201, dependencies=[Depends(rate_limit("jobs", 30))])
def add_job(body: JobTextIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _intake(db, user, [body])


@router.post("/bulk", status_code=201, dependencies=[Depends(rate_limit("jobs-bulk", 10))])
def add_jobs_bulk(body: JobBulkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _intake(db, user, body.items)


@router.post("/upload", status_code=201, dependencies=[Depends(rate_limit("jobs-upload", 10))])
async def upload_jobs(files: list[UploadFile] = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if len(files) > get_settings().max_bulk_jobs:
        raise HTTPException(413, "Too many files in one request.")
    _reserve(db, user, len(files))
    batch = uuid.uuid4()
    jobs: list[Job] = []
    for f in files:
        data = await f.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
        try:
            kind = sniff_kind(data, f.filename or "")
            doc = extract_text(data, f.filename or "")
            key = new_key(user.id, "job-sources", {"pdf": "pdf", "docx": "docx", "image": "img", "text": "txt"}[kind])
            get_storage().put(key, data)
            jobs.append(_new_job(db, user, batch, {"image": "image", "pdf": "pdf", "docx": "docx", "text": "text"}[kind], doc.text, "", key, f.filename))
        except DocumentError as e:
            jobs.append(_new_job(db, user, batch, "image" if (f.content_type or "").startswith("image") else "pdf", "", "", None, f.filename, fail_reason=e.reason))
        usage.record_usage(db, user.id, "job_analyses", 1)
    audit(db, user.id, "jobs.upload", entity_type="job_batch", entity_id=batch, count=len(jobs))
    db.commit()
    for j in jobs:
        if j.status == "queued":
            enqueue("process_job", str(j.id))
    return _batch_response(db, user, batch)


@router.post("/parse")
def parse_preview(body: JobTextIn, user: User = Depends(get_current_user)):
    """Instant, free, rule-based parse for previewing a pasted post. Nothing is stored and no AI credits are used."""
    if not body.text:
        raise HTTPException(422, "Paste the job text.")
    return parse_job_text(body.text).model_dump(mode="json")


@router.post("/manual", status_code=201)
def manual_job(body: JobPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Enter a job by hand (used when parsing fails, e.g. blurry screenshot)."""
    if not (body.job_title or body.company_name):
        raise HTTPException(422, "Enter at least a job title or company.")
    usage.check_quota(db, user, "job_analyses", 1)
    batch = uuid.uuid4()
    job = _new_job(db, user, batch, "manual", f"{body.job_title or ''} at {body.company_name or ''}\n" + "\n".join(body.responsibilities or []))
    _apply_patch(job, body)
    job.status = "completed"
    job.content_hash = ""
    c = pipeline.get_or_create_company(db, user.id, job.company_name)
    job.company_id = c.id if c else None
    usage.record_usage(db, user.id, "job_analyses", 1)
    db.commit()
    pipeline.match_job(db, user, job)
    db.commit()
    return job_out(job, db.scalar(select(JobMatch).where(JobMatch.job_id == job.id)))


@router.post("/analyze")
def analyze(body: JobAnalyzeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """(Re)run extraction + matching for existing jobs."""
    jobs = [get_owned(db, Job, i, user) for i in body.job_ids]
    for j in jobs:
        j.status = "queued"
    db.commit()
    for j in jobs:
        if j.original_content:
            enqueue("process_job", str(j.id))
        else:
            j.status, j.status_reason = "failed", "There is no job text to analyse. Paste the text or enter the details manually."
    db.commit()
    db.expire_all()
    rows = [(db.get(Job, j.id), db.scalar(select(JobMatch).where(JobMatch.job_id == j.id))) for j in jobs]
    return {"jobs": [job_out(j, m) for j, m in rows], "summary": _summary(rows)}


@router.get("")
def list_jobs(status: str | None = None, classification: str | None = None, q: str | None = Query(default=None, max_length=100),
              sort: str = Query(default="recent", pattern="^(recent|urgency|score)$"), hide_duplicates: bool = False, batch_id: uuid.UUID | None = None,
              limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = (select(Job, JobMatch, Application).outerjoin(JobMatch, JobMatch.job_id == Job.id).outerjoin(Application, (Application.job_id == Job.id) & (Application.deleted_at.is_(None)))
            .where(Job.user_id == user.id, Job.deleted_at.is_(None)))
    if status:
        stmt = stmt.where(Job.status == status)
    if classification:
        stmt = stmt.where(JobMatch.classification == classification)
    if batch_id:
        stmt = stmt.where(Job.batch_id == batch_id)
    if hide_duplicates:
        stmt = stmt.where(Job.duplicate_of_id.is_(None))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Job.job_title).like(like) | func.lower(Job.company_name).like(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if sort == "urgency":
        stmt = stmt.order_by(Job.deadline.is_(None), Job.deadline.asc(), Job.created_at.desc())
    elif sort == "score":
        stmt = stmt.order_by(JobMatch.score.desc().nulls_last(), Job.created_at.desc())
    else:
        stmt = stmt.order_by(Job.created_at.desc())
    rows = db.execute(stmt.limit(limit).offset(offset)).all()
    return {"total": total, "items": [job_out(j, m, a) for j, m, a in rows]}


@router.get("/{job_id}")
def get_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = get_owned(db, Job, job_id, user)
    m = db.scalar(select(JobMatch).where(JobMatch.job_id == j.id))
    a = db.scalar(select(Application).where(Application.job_id == j.id, Application.deleted_at.is_(None)))
    out = job_out(j, m, a)
    out["original_content"] = j.original_content
    return out


def _apply_patch(job: Job, body: JobPatch) -> None:
    d = body.model_dump(exclude_unset=True)
    for k in ("company_name", "job_title", "location", "employment_type", "workplace_type", "salary", "application_email", "application_url", "responsibilities", "deadline"):
        if k in d:
            setattr(job, k, d[k] if d[k] is not None else ("" if k != "responsibilities" else []))
    for k in ("required_skills", "preferred_skills", "tech_stack"):
        if k in d and d[k] is not None:
            setattr(job, k, list(dict.fromkeys(canonicalize(s) for s in d[k] if s.strip())))
    if "min_years" in d or "max_years" in d:
        job.experience_required = {**(job.experience_required or {}), **{k: d[k] for k in ("min_years", "max_years") if k in d}}
    if "education_level" in d:
        job.education_required = {**(job.education_required or {}), "level": d["education_level"] or ""}


@router.patch("/{job_id}")
def patch_job(job_id: uuid.UUID, body: JobPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = get_owned(db, Job, job_id, user)
    _apply_patch(j, body)
    if j.job_title:
        j.status, j.status_reason = "completed", None
    c = pipeline.get_or_create_company(db, user.id, j.company_name)
    j.company_id = c.id if c else None
    db.commit()
    m = pipeline.match_job(db, user, j)
    db.commit()
    return job_out(j, m)


@router.post("/{job_id}/ats-score")
def score_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = get_owned(db, Job, job_id, user)
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if not profile: raise HTTPException(422, "Complete your profile before scoring a CV against this job.")
    score, report = ats_score(profile, job)
    job.ats_score, job.ats_report = score, report
    db.commit()
    return {"score": score, **report}


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = get_owned(db, Job, job_id, user)
    j.deleted_at = utcnow()
    for a in db.scalars(select(Application).where(Application.job_id == j.id)):
        a.deleted_at = utcnow()
    audit(db, user.id, "job.delete", entity_type="job", entity_id=j.id)
    db.commit()


@router.post("/{job_id}/retry")
def retry(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = get_owned(db, Job, job_id, user)
    if j.source_url and not j.original_content and j.source == "url":
        try:
            j.original_content, j.source_url = fetch_job_page(j.source_url)
        except FetchError as e:
            j.status, j.status_reason = "failed", e.reason
            db.commit()
            return job_out(j)
    if not j.original_content:
        raise HTTPException(422, "There is no text to analyse. Paste the job text or enter the details manually.")
    j.status = "queued"
    db.commit()
    enqueue("process_job", str(j.id))
    db.expire_all()
    j = db.get(Job, job_id)
    return job_out(j, db.scalar(select(JobMatch).where(JobMatch.job_id == j.id)))


@router.post("/{job_id}/not-duplicate")
def not_duplicate(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The user confirms this job is not a duplicate, so it is included in matches and lists."""
    j = get_owned(db, Job, job_id, user)
    j.duplicate_of_id = j.duplicate_score = None
    j.extracted_information = {**(j.extracted_information or {}), "duplicate_reasons": [], "duplicate_dismissed": True}
    db.commit()
    return job_out(j, db.scalar(select(JobMatch).where(JobMatch.job_id == j.id)))
