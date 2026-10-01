from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.helpers import resume_out
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user, get_owned
from app.core.ratelimit import rate_limit
from app.models import Certification, Education, Experience, Profile, Project, Resume, ResumeVersion, Skill, User
from app.models.base import utcnow
from app.services import usage
from app.services.audit import audit
from app.services.parsing.documents import DocumentError, check_size, sniff_kind
from app.services.storage import get_storage, new_key, signed_download_token
from app.workers.dispatch import enqueue

router = APIRouter(prefix="/resumes", tags=["resumes"])
ALLOWED = {"pdf", "docx"}


@router.post("/upload", status_code=201, dependencies=[Depends(rate_limit("upload", 20))])
async def upload_resume(request: Request, file: UploadFile = File(...), label: str = Form("Master CV"), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    try:
        check_size(data)
        kind = sniff_kind(data, file.filename or "")
    except DocumentError as e:
        raise HTTPException(413 if e.code == "too_large" else 422, e.reason)
    if kind not in ALLOWED:
        raise HTTPException(422, "Please upload your CV as a PDF or DOCX file.")
    sha = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Resume).where(Resume.user_id == user.id, Resume.sha256 == sha, Resume.deleted_at.is_(None)))
    if existing:
        return {**resume_out(existing), "duplicate": True}
    plan = usage.user_plan(db, user.id)
    live = db.scalar(select(func.count()).select_from(Resume).where(Resume.user_id == user.id, Resume.deleted_at.is_(None))) or 0
    _, lim = usage.limit_for(db, plan, "resumes")
    if live >= lim:
        raise HTTPException(402, detail={"code": "quota_exceeded", "metric": "resumes", "limit": lim, "message": f"Your {plan} plan allows {lim} CVs. Delete one or upgrade."})
    key = new_key(user.id, "resumes", kind)
    get_storage().put(key, data, file.content_type or "application/octet-stream")
    first = live == 0
    r = Resume(user_id=user.id, filename=(file.filename or f"cv.{kind}")[:255], content_type=file.content_type or kind, size_bytes=len(data), storage_key=key, sha256=sha,
               is_master=first, label=label[:100] or "Master CV")
    db.add(r)
    audit(db, user.id, "resume.upload", entity_type="resume", entity_id=r.id, request=request, size=len(data))
    db.commit()
    enqueue("process_resume", str(r.id))
    db.expire_all()
    return resume_out(db.get(Resume, r.id))


@router.get("")
def list_resumes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Resume).where(Resume.user_id == user.id, Resume.deleted_at.is_(None)).order_by(Resume.created_at.desc())).all()
    return [resume_out(r) for r in rows]


@router.get("/versions")
def list_versions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ResumeVersion).where(ResumeVersion.user_id == user.id).order_by(ResumeVersion.created_at.desc()).limit(200)).all()
    return [{"id": str(v.id), "label": v.label, "role_type": v.role_type, "template": v.template, "application_id": str(v.application_id) if v.application_id else None,
             "created_at": v.created_at.isoformat(), "target": v.content.get("meta", {}).get("target_title"), "company": v.content.get("meta", {}).get("target_company")} for v in rows]


@router.get("/{resume_id}")
def get_resume(resume_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = get_owned(db, Resume, resume_id, user)
    return resume_out(r)


@router.post("/{resume_id}/reparse")
def reparse(resume_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = get_owned(db, Resume, resume_id, user)
    r.status = "queued"
    db.commit()
    enqueue("process_resume", str(r.id))
    db.expire_all()
    return resume_out(db.get(Resume, r.id))


@router.get("/{resume_id}/download")
def download_url(resume_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = get_owned(db, Resume, resume_id, user)
    tok = signed_download_token(user.id, r.storage_key, r.filename, r.content_type)
    return {"url": f"{get_settings().api_base_url}/api/v1/files/{tok}", "expires_in": get_settings().signed_url_seconds}


@router.delete("/{resume_id}", status_code=204)
def delete_resume(resume_id: uuid.UUID, request: Request, delete_profile_data: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Permanently removes the uploaded file and extracted text. Optionally also clears the structured profile derived from it."""
    r = get_owned(db, Resume, resume_id, user)
    get_storage().delete(r.storage_key)
    r.deleted_at, r.extracted_text, r.status = utcnow(), "", "deleted"
    p = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if p and p.source_resume_id == r.id:
        p.source_resume_id = None
        if delete_profile_data:
            for model in (Skill, Experience, Education, Project, Certification):
                db.execute(delete(model).where(model.profile_id == p.id))
            p.summary = p.headline = ""
    audit(db, user.id, "resume.delete", entity_type="resume", entity_id=r.id, request=request, profile_cleared=delete_profile_data)
    db.commit()
