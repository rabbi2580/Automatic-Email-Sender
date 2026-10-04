from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, get_owned
from app.models import Application, ApplicationEmail, FollowUpDraft, FollowUpRule, IncomingMessage, Job, User
from app.models.base import utcnow
from app.schemas.api import FollowUpPatch, FollowUpRuleIn
from app.services.delivery import service as delivery
from app.services.delivery.service import SendBlocked

router = APIRouter(prefix="/follow-ups", tags=["follow-ups"])


def _hash(to: str, subject: str, body: str) -> str:
    return hashlib.sha256(f"{to}\n{subject}\n{body}".encode()).hexdigest()


def _out(d: FollowUpDraft, job: Job | None = None) -> dict:
    return {"id": str(d.id), "application_id": str(d.application_id), "sequence": d.sequence, "status": d.status,
            "to": d.to_address, "subject": d.subject, "body": d.body, "content_hash": d.content_hash,
            "needs_input": d.needs_input, "due_at": d.due_at.isoformat() if d.due_at else None,
            "approved_at": d.approved_at.isoformat() if d.approved_at else None, "sent_at": d.sent_at.isoformat() if d.sent_at else None,
            "company": job.company_name if job else None, "position": job.job_title if job else None}


@router.get("")
def list_followups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(FollowUpDraft, Job).join(Application, Application.id == FollowUpDraft.application_id).join(Job, Job.id == Application.job_id)
                      .where(FollowUpDraft.user_id == user.id).order_by(FollowUpDraft.created_at.desc()).limit(100)).all()
    return [_out(d, j) for d, j in rows]


@router.get("/settings")
def get_rule(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.scalar(select(FollowUpRule).where(FollowUpRule.user_id == user.id))
    if not rule:
        rule = FollowUpRule(user_id=user.id); db.add(rule); db.commit(); db.refresh(rule)
    return {"default_wait_days": rule.default_wait_days, "max_followups": rule.max_followups, "stop_on_reply": rule.stop_on_reply, "enabled": rule.enabled}


@router.put("/settings")
def put_rule(body: FollowUpRuleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.scalar(select(FollowUpRule).where(FollowUpRule.user_id == user.id))
    if not rule:
        rule = FollowUpRule(user_id=user.id); db.add(rule)
    for k, v in body.model_dump().items(): setattr(rule, k, v)
    db.commit()
    return get_rule(user, db)


@router.post("/from-application/{app_id}")
def create_followup(app_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = get_owned(db, Application, app_id, user)
    if app.status not in {"sent", "application_confirmed", "interview"}:
        raise HTTPException(409, "Follow-ups are available after an application is sent.")
    rule = db.scalar(select(FollowUpRule).where(FollowUpRule.user_id == user.id)) or FollowUpRule(user_id=user.id)
    if not rule.enabled:
        raise HTTPException(409, "Follow-ups are disabled in your settings.")
    count = db.scalar(select(func.count()).select_from(FollowUpDraft).where(FollowUpDraft.user_id == user.id, FollowUpDraft.application_id == app.id,
                                                                    FollowUpDraft.status != "cancelled")) or 0
    if count >= rule.max_followups:
        raise HTTPException(409, "The follow-up limit for this application has been reached.")
    if rule.stop_on_reply and db.scalar(select(IncomingMessage.id).where(IncomingMessage.user_id == user.id, IncomingMessage.application_id == app.id,
                                                                          IncomingMessage.classification.in_(["reply", "interview", "rejection", "complaint"]))):
        raise HTTPException(409, "A reply has already been detected for this application.")
    em = db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == app.id))
    job = db.get(Job, app.job_id)
    if not em or not em.to_address or not job:
        raise HTTPException(422, "The application is missing a recipient or job details.")
    sequence = int(count) + 1
    subject = em.subject if em.subject.lower().startswith("re:") else f"Following up: {em.subject}"
    body = (f"Hello,\n\nI’m following up on my application for the {job.job_title} position at {job.company_name}. "
            "I remain very interested in the opportunity and would be glad to provide any additional information.\n\n"
            "Thank you for your time.\n\nBest regards")
    now = utcnow()
    draft = FollowUpDraft(user_id=user.id, application_id=app.id, sequence=sequence, to_address=em.to_address, subject=subject, body=body,
                          content_hash=_hash(em.to_address, subject, body), due_at=(app.sent_at or now) + timedelta(days=rule.default_wait_days))
    db.add(draft); db.commit(); db.refresh(draft)
    return _out(draft, job)


@router.patch("/{draft_id}")
def patch_followup(draft_id: uuid.UUID, body: FollowUpPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    draft = get_owned(db, FollowUpDraft, draft_id, user)
    if draft.status != "draft": raise HTTPException(409, "Only draft follow-ups can be edited.")
    data = body.model_dump(exclude_unset=True)
    if "subject" in data: draft.subject = data["subject"].strip()
    if "body" in data: draft.body = data["body"].strip()
    draft.content_hash = _hash(draft.to_address, draft.subject, draft.body); draft.needs_input = len(draft.body) < 20
    db.commit()
    return _out(draft, db.scalar(select(Job).join(Application, Application.job_id == Job.id).where(Application.id == draft.application_id)))


@router.post("/{draft_id}/approve")
def approve_followup(draft_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    draft = get_owned(db, FollowUpDraft, draft_id, user)
    if draft.status != "draft": raise HTTPException(409, "Only draft follow-ups can be approved.")
    if draft.needs_input or not draft.body.strip(): raise HTTPException(422, "Complete the follow-up before approving it.")
    app = get_owned(db, Application, draft.application_id, user)
    if app.status not in {"sent", "application_confirmed", "interview"}: raise HTTPException(409, "This application cannot receive a follow-up.")
    draft.status, draft.approved_at = "approved", utcnow()
    db.commit()
    return _out(draft, db.get(Job, app.job_id))


@router.post("/{draft_id}/send/preview")
def preview_send(draft_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try: return delivery.preview_followup(db, user, draft_id)
    except SendBlocked as e: raise HTTPException(404 if e.code == "not_found" else 409, e.message)


@router.post("/{draft_id}/send")
def send_followup(draft_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try: return delivery.send_followup(db, user, draft_id)
    except SendBlocked as e: raise HTTPException(409, detail={"code": e.code, "message": e.message})
