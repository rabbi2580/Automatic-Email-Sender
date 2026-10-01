from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.helpers import application_summary, doc_out, email_out, job_out, match_out
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user, get_owned
from app.core.ratelimit import rate_limit
from app.models import (
    Application, ApplicationDocument, ApplicationEmail, ApplicationEvent, CoverLetter, EmailAccount, Job, JobMatch, ResumeVersion, User,
)
from app.schemas.api import ApplicationPatch, BulkApproveIn, CoverLetterPatch, EmailPatch, GenerateIn, RegenerateIn, SendIn, SendPreviewIn
from app.services import exporters_facade as fx
from app.services import pipeline, usage
from app.services.audit import audit
from app.services.delivery import service as delivery
from app.services.delivery.service import SendBlocked
from app.services.profile_view import profile_snapshot
from app.services.storage import get_storage, signed_download_token
from app.services.workflow import TransitionError, transition
from app.workers.dispatch import enqueue

router = APIRouter(prefix="/applications", tags=["applications"])


def _app(db: Session, user: User, app_id: uuid.UUID) -> Application:
    return get_owned(db, Application, app_id, user)


def _detail(db: Session, a: Application) -> dict:
    j = db.get(Job, a.job_id)
    m = db.get(JobMatch, a.match_id) if a.match_id else db.scalar(select(JobMatch).where(JobMatch.job_id == j.id))
    cl = db.scalar(select(CoverLetter).where(CoverLetter.application_id == a.id))
    em = db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == a.id))
    rv = db.scalar(select(ResumeVersion).where(ResumeVersion.application_id == a.id))
    docs = db.scalars(select(ApplicationDocument).where(ApplicationDocument.application_id == a.id)).all()
    events = db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == a.id).order_by(ApplicationEvent.created_at)).all()
    out = application_summary(a, j, m)
    out.update({
        "job": job_out(j, m), "match": match_out(m) if m else None, "tone": a.tone, "language": a.language, "qc": a.qc_report, "linkedin_message": a.linkedin_message,
        "cover_letter": {"body": cl.body, "tone": cl.tone, "edited_by_user": cl.edited_by_user, "source": (cl.grounding or {}).get("source")} if cl else None,
        "email": email_out(em), "documents": [doc_out(d) for d in docs],
        "cv": {"label": rv.label, "role_type": rv.role_type, "template": rv.template, "options": rv.options, "content": rv.content} if rv else None,
        "events": [{"type": e.type, "from": e.from_status, "to": e.to_status, "at": e.created_at.isoformat(), "detail": e.detail} for e in events],
        "ai_disclosure": "Drafted with AI from your own profile. Review everything before approving. Outcomes are decided by employers, not by this tool.",
    })
    return out


def _revoke_approval(db: Session, a: Application, why: str) -> None:
    if a.status == "approved":
        transition(db, a, "awaiting_review", detail={"reason": why})
    a.approved_at, a.content_hash = None, ""


@router.post("/generate", status_code=202, dependencies=[Depends(rate_limit("generate", 20))])
def generate(body: GenerateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = [get_owned(db, Job, jid, user) for jid in body.job_ids]
    todo = [j for j in jobs if j.status in ("completed", "requires_review") and j.job_title]
    skipped = [{"job_id": str(j.id), "reason": "Job has not been analysed successfully."} for j in jobs if j not in todo]
    usage.check_quota(db, user, "ai_generations", len(todo))
    opts = {k: v for k, v in {"template": body.template, "font": body.font, "pages": body.pages, "include_cover_letter": body.include_cover_letter}.items() if v is not None}
    for j in todo:
        usage.record_usage(db, user.id, "ai_generations", 1, job_id=str(j.id))
    db.commit()
    for j in todo:
        enqueue("generate_application", str(user.id), str(j.id), body.tone, body.language, opts)
    db.expire_all()
    out = []
    for j in todo:
        a = db.scalar(select(Application).where(Application.user_id == user.id, Application.job_id == j.id))
        if a:
            out.append(application_summary(a, db.get(Job, j.id), db.scalar(select(JobMatch).where(JobMatch.job_id == j.id))))
    audit(db, user.id, "applications.generate", count=len(todo))
    db.commit()
    return {"applications": out, "skipped": skipped}


@router.get("")
def list_applications(status: str | None = None, q: str | None = Query(default=None, max_length=100), sort: str = Query(default="updated", pattern="^(updated|urgency|score)$"),
                      limit: int = Query(default=100, ge=1, le=300), offset: int = Query(default=0, ge=0), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = (select(Application, Job, JobMatch).join(Job, Job.id == Application.job_id).outerjoin(JobMatch, JobMatch.job_id == Job.id)
            .where(Application.user_id == user.id, Application.deleted_at.is_(None)))
    if status:
        stmt = stmt.where(Application.status == status)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Job.job_title).like(like) | func.lower(Job.company_name).like(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = {"urgency": stmt.order_by(Job.deadline.is_(None), Job.deadline.asc()), "score": stmt.order_by(JobMatch.score.desc().nulls_last()),
            "updated": stmt.order_by(Application.updated_at.desc())}[sort]
    rows = db.execute(stmt.limit(limit).offset(offset)).all()
    return {"total": total, "items": [application_summary(a, j, m) for a, j, m in rows]}


@router.post("/approve-bulk")
def approve_bulk(body: BulkApproveIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    results = []
    for aid in body.application_ids:
        try:
            a = _app(db, user, aid)
            delivery.approve_application(db, user, a)
            results.append({"application_id": str(aid), "ok": True})
        except SendBlocked as e:
            results.append({"application_id": str(aid), "ok": False, "message": e.message})
        except HTTPException as e:
            results.append({"application_id": str(aid), "ok": False, "message": str(e.detail)})
    return {"results": results, "approved": sum(r["ok"] for r in results)}


@router.post("/send/preview")
def send_preview(body: SendPreviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return delivery.preview_send(db, user, body.application_ids)


@router.post("/send", dependencies=[Depends(rate_limit("send", 10, per_user=True))])
def send(body: SendIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(422, "Explicit confirmation is required to send applications.")
    try:
        results = delivery.send_applications(db, user, body.application_ids, body.confirmation_token, request)
    except SendBlocked as e:
        raise HTTPException(409 if e.code != "email_unverified" else 403, detail={"code": e.code, "message": e.message})
    return {"results": results, "sent": sum(r["status"] == "sent" for r in results)}


@router.get("/{app_id}")
def get_application(app_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _detail(db, _app(db, user, app_id))


@router.patch("/{app_id}")
def patch_application(app_id: uuid.UUID, body: ApplicationPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = _app(db, user, app_id)
    d = body.model_dump(exclude_unset=True)
    if "notes" in d:
        a.notes = d["notes"] or ""
    if "reminder_at" in d:
        a.reminder_at = d["reminder_at"]
    if d.get("status"):
        if d["status"] in ("approved", "sent"):
            raise HTTPException(422, "Use the approve / send actions for this status.")
        try:
            transition(db, a, d["status"], actor="user")
        except TransitionError as e:
            raise HTTPException(409, str(e))
    db.commit()
    return _detail(db, a)


@router.post("/{app_id}/approve")
def approve(app_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = _app(db, user, app_id)
    try:
        delivery.approve_application(db, user, a)
    except SendBlocked as e:
        raise HTTPException(422, detail={"code": e.code, "message": e.message, "qc": a.qc_report})
    return _detail(db, a)


@router.post("/{app_id}/reject")
def reject(app_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The reviewer declines this prepared application. It will not be sent; it can be regenerated later."""
    a = _app(db, user, app_id)
    if a.status in ("sent", "application_confirmed", "interview", "offer", "rejected"):
        raise HTTPException(409, "This application was already sent.")
    a.approved_at, a.content_hash = None, ""
    transition(db, a, "withdrawn", actor="user", force=True, detail={"reason": "rejected_by_reviewer"})
    db.commit()
    return _detail(db, a)


@router.post("/{app_id}/qc")
def rerun_qc(app_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = _app(db, user, app_id)
    return pipeline.run_application_qc(db, a)


@router.post("/{app_id}/regenerate", status_code=202)
def regenerate(app_id: uuid.UUID, body: RegenerateIn | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = _app(db, user, app_id)
    if a.status in ("sent", "application_confirmed", "interview", "offer", "rejected"):
        raise HTTPException(409, "This application was already sent.")
    usage.check_quota(db, user, "ai_generations", 1)
    usage.record_usage(db, user.id, "ai_generations", 1, job_id=str(a.job_id))
    db.commit()
    opts = {}
    if body:
        opts = {k: v for k, v in {"template": body.template, "font": body.font, "pages": body.pages, "include_cover_letter": body.include_cover_letter}.items() if v is not None}
    enqueue("generate_application", str(user.id), str(a.job_id), body.tone if body else None, body.language if body else None, opts)
    db.expire_all()
    return _detail(db, _app(db, user, app_id))


@router.patch("/{app_id}/cover-letter")
def edit_cover_letter(app_id: uuid.UUID, body: CoverLetterPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = _app(db, user, app_id)
    if a.status in ("sent", "application_confirmed", "interview", "offer", "rejected"):
        raise HTTPException(409, "This application was already sent.")
    cl = db.scalar(select(CoverLetter).where(CoverLetter.application_id == a.id))
    if not cl:
        raise HTTPException(404, "No cover letter yet.")
    cl.body, cl.edited_by_user = body.body, True
    letter = pipeline.text_to_letter(body.body)
    profile = fx.get_profile(db, user)
    header = {"name": profile.full_name, "email": profile.email, "phone": profile.phone, "location": profile.location}
    rv = db.scalar(select(ResumeVersion).where(ResumeVersion.application_id == a.id))
    for d in db.scalars(select(ApplicationDocument).where(ApplicationDocument.application_id == a.id, ApplicationDocument.kind.in_(("cover_letter_pdf", "cover_letter_docx")))):
        try:
            data = fx.render_letter(d.kind, letter, header, {**(rv.options if rv else {}), "language": cl.language})
        except fx.exporters.ComplexScriptUnavailable:
            continue  # PDF cannot be shaped on this server; the DOCX copy is still refreshed
        get_storage().put(d.storage_key, data, d.content_type)
        d.size_bytes, d.sha256 = len(data), hashlib.sha256(data).hexdigest()
    _revoke_approval(db, a, "cover_letter_edited")
    pipeline.run_application_qc(db, a, commit=False)
    db.commit()
    return _detail(db, a)


@router.patch("/{app_id}/email")
def edit_email(app_id: uuid.UUID, body: EmailPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = _app(db, user, app_id)
    if a.status in ("sent", "application_confirmed", "interview", "offer", "rejected"):
        raise HTTPException(409, "This application was already sent.")
    em = db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == a.id))
    if not em:
        raise HTTPException(404, "No email draft yet.")
    d = body.model_dump(exclude_unset=True)
    for k in ("to_address", "subject", "body"):
        if k in d and d[k] is not None:
            setattr(em, k, d[k].strip() if k != "body" else d[k])
    if d.get("attachment_doc_ids") is not None:
        ids = {str(i) for i in d["attachment_doc_ids"]}
        own = {str(x.id) for x in db.scalars(select(ApplicationDocument).where(ApplicationDocument.application_id == a.id))}
        if not ids <= own:
            raise HTTPException(422, "Attachments must belong to this application.")
        em.attachment_doc_ids = sorted(ids)
    if d.get("email_account_id"):
        acct = get_owned(db, EmailAccount, d["email_account_id"], user)
        em.email_account_id = acct.id
    em.edited_by_user = True
    _revoke_approval(db, a, "email_edited")
    pipeline.run_application_qc(db, a, commit=False)
    db.commit()
    return _detail(db, a)


@router.post("/{app_id}/mark-applied")
def mark_applied(app_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = _app(db, user, app_id)
    try:
        delivery.mark_applied_manually(db, user, a)
    except SendBlocked as e:
        raise HTTPException(409, e.message)
    return _detail(db, a)


@router.get("/{app_id}/documents/{doc_id}/url")
def document_url(app_id: uuid.UUID, doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = _app(db, user, app_id)
    d = get_owned(db, ApplicationDocument, doc_id, user)
    if d.application_id != a.id:
        raise HTTPException(404, "Not found")
    tok = signed_download_token(user.id, d.storage_key, d.filename, d.content_type)
    return {"url": f"{get_settings().api_base_url}/api/v1/files/{tok}", "filename": d.filename, "expires_in": get_settings().signed_url_seconds}
