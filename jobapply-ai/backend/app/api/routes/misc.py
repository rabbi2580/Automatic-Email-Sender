from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import verify_password
from app.models import (
    Application, ApplicationEmail, ApplicationEvent, AuditLog, CalendarEvent, CoverLetter, EmailAccount, FollowUpDraft, FollowUpRule, IncomingMessage, InterviewPrep, Job, JobMatch, Notification, Profile, Resume, ResumeVersion, SendLog, User,
)
from app.models.base import utcnow
from app.schemas.api import DeleteAccountIn, NotificationAction, SettingsIn, TrainingOptIn
from app.services import usage
from app.services.audit import audit
from app.services.matching.engine import normalise_thresholds, normalise_weights
from app.services.parsing.deadlines import days_remaining, urgency_label
from app.services.profile_view import profile_snapshot
from app.services.storage import get_storage
from app.services.user_settings import get_user_settings

router = APIRouter(tags=["account"])


@router.get("/analytics")
def analytics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    uid = user.id
    jobs = db.scalar(select(func.count()).select_from(Job).where(Job.user_id == uid, Job.deleted_at.is_(None), Job.duplicate_of_id.is_(None))) or 0
    cls = dict(db.execute(select(JobMatch.classification, func.count()).join(Job, Job.id == JobMatch.job_id).where(
        Job.user_id == uid, Job.deleted_at.is_(None), Job.duplicate_of_id.is_(None)).group_by(JobMatch.classification)).all())
    st = dict(db.execute(select(Application.status, func.count()).where(Application.user_id == uid, Application.deleted_at.is_(None)).group_by(Application.status)).all())
    sent_total = sum(st.get(k, 0) for k in ("sent", "application_confirmed", "interview", "offer", "rejected"))
    responded = sum(st.get(k, 0) for k in ("interview", "offer", "rejected"))
    upcoming = db.execute(select(Job).where(Job.user_id == uid, Job.deleted_at.is_(None), Job.deadline.is_not(None), Job.deadline >= date.today(),
                                            Job.deadline <= date.today() + timedelta(days=14)).order_by(Job.deadline).limit(10)).scalars().all()
    reminders = db.execute(select(Application, Job).join(Job, Job.id == Application.job_id).where(Application.user_id == uid, Application.reminder_at.is_not(None),
                           Application.deleted_at.is_(None)).order_by(Application.reminder_at).limit(10)).all()
    return {
        "cards": {"jobs_added": jobs, "strong_matches": cls.get("strong", 0), "pending_review": st.get("awaiting_review", 0) + st.get("approved", 0),
                  "applications_sent": sent_total, "interviews": st.get("interview", 0), "rejected": st.get("rejected", 0), "offers": st.get("offer", 0),
                  "response_rate": round(100 * responded / sent_total, 1) if sent_total else 0.0},
        "classification": {k: cls.get(k, 0) for k in ("strong", "potential", "weak", "not_suitable")},
        "funnel": st,
        "upcoming_deadlines": [{"job_id": str(j.id), "title": j.job_title, "company": j.company_name, "deadline": j.deadline.isoformat(), "days_remaining": days_remaining(j.deadline),
                                "urgency": urgency_label(days_remaining(j.deadline))} for j in upcoming],
        "reminders": [{"application_id": str(a.id), "title": j.job_title, "company": j.company_name, "reminder_at": a.reminder_at.isoformat()} for a, j in reminders],
        "disclaimer": "Scores and statuses are AI-assisted estimates and your own records. They do not reflect any employer decision.",
    }


@router.get("/usage")
def my_usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return usage.usage_summary(db, user.id)


@router.get("/settings")
def get_settings_route(user: User = Depends(get_current_user)):
    return get_user_settings(user)


@router.put("/settings")
def put_settings(body: SettingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cur = dict(user.settings or {})
    d = body.model_dump(exclude_unset=True)
    if d.get("weights") is not None:
        if sum(d["weights"].values()) <= 0:
            raise HTTPException(422, "At least one weight must be above zero.")
        d["weights"] = normalise_weights(d["weights"])
    if d.get("thresholds") is not None:
        t = {**get_user_settings(user)["thresholds"], **d["thresholds"]}
        if not (t["strong"] >= t["potential"] >= t["weak"] >= 0) or t["strong"] > 100:
            raise HTTPException(422, "Thresholds must satisfy strong ≥ potential ≥ weak, within 0–100.")
        d["thresholds"] = t
    cur.update({k: v for k, v in d.items() if v is not None})
    user.settings = cur
    db.commit()
    return get_user_settings(user)


@router.get("/notifications")
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.dismissed_at.is_(None), Notification.snoozed_until.is_(None) | (Notification.snoozed_until <= now),
                                                    (Notification.due_at.is_(None)) | (Notification.due_at <= now)).order_by(Notification.created_at.desc()).limit(50)).all()
    return [{"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "entity_type": n.entity_type, "entity_id": n.entity_id, "read": n.read_at is not None,
             "created_at": n.created_at.isoformat()} for n in rows]


@router.patch("/notifications/{notification_id}")
def notification_action(notification_id: uuid.UUID, body: NotificationAction, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if not n: raise HTTPException(404, "Notification not found")
    if body.action == "read": n.read_at = utcnow()
    elif body.action == "dismiss": n.dismissed_at = utcnow()
    else:
        if not body.until: raise HTTPException(422, "until is required when snoozing")
        if body.until <= utcnow(): raise HTTPException(422, "snooze time must be in the future")
        n.snoozed_until = body.until
    db.commit(); return {"ok": True}


# ------------------------------------------------------------------ privacy -------------------------------------------------------
@router.get("/privacy/export")
def export_data(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """GDPR-style export of everything we store about you (credentials and storage keys are never included)."""
    p = db.scalar(select(Profile).where(Profile.user_id == user.id))
    apps = db.scalars(select(Application).where(Application.user_id == user.id)).all()
    data = {
        "exported_at": utcnow().isoformat(),
        "account": {"id": str(user.id), "email": user.email, "full_name": user.full_name, "locale": user.locale, "created_at": user.created_at.isoformat(),
                    "ai_training_opt_in": user.ai_training_opt_in, "settings": user.settings},
        "profile": profile_snapshot(p) if p else None,
        "resumes": [{"id": str(r.id), "filename": r.filename, "label": r.label, "created_at": r.created_at.isoformat(), "extracted_text": r.extracted_text}
                    for r in db.scalars(select(Resume).where(Resume.user_id == user.id, Resume.deleted_at.is_(None)))],
        "jobs": [{"id": str(j.id), "company": j.company_name, "title": j.job_title, "location": j.location, "deadline": j.deadline.isoformat() if j.deadline else None,
                  "required_skills": j.required_skills, "application_email": j.application_email, "original_content": j.original_content}
                 for j in db.scalars(select(Job).where(Job.user_id == user.id, Job.deleted_at.is_(None)))],
        "matches": [{"job_id": str(m.job_id), "score": m.score, "classification": m.classification, "explanation": m.explanation} for m in db.scalars(select(JobMatch).where(JobMatch.user_id == user.id))],
        "applications": [{"id": str(a.id), "job_id": str(a.job_id), "status": a.status, "notes": a.notes, "sent_at": a.sent_at.isoformat() if a.sent_at else None,
                          "cover_letter": (db.scalar(select(CoverLetter.body).where(CoverLetter.application_id == a.id)) or ""),
                          "email": (lambda e: {"to": e.to_address, "subject": e.subject, "body": e.body, "status": e.status} if e else None)(
                              db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == a.id)))} for a in apps],
        "tailored_cvs": [{"id": str(v.id), "label": v.label, "content": v.content} for v in db.scalars(select(ResumeVersion).where(ResumeVersion.user_id == user.id))],
        "email_accounts": [{"provider": a.provider, "address": a.address, "status": a.status} for a in db.scalars(select(EmailAccount).where(EmailAccount.user_id == user.id, EmailAccount.deleted_at.is_(None)))],
        "incoming_messages": [{"id": str(m.id), "application_id": str(m.application_id) if m.application_id else None, "provider": m.provider, "from": m.from_address,
                               "subject": m.subject, "snippet": m.snippet, "classification": m.classification, "received_at": m.received_at.isoformat() if m.received_at else None}
                              for m in db.scalars(select(IncomingMessage).where(IncomingMessage.user_id == user.id))],
        "follow_up_rules": [{"default_wait_days": r.default_wait_days, "max_followups": r.max_followups, "stop_on_reply": r.stop_on_reply, "enabled": r.enabled}
                             for r in db.scalars(select(FollowUpRule).where(FollowUpRule.user_id == user.id))],
        "follow_up_drafts": [{"id": str(d.id), "application_id": str(d.application_id), "sequence": d.sequence, "status": d.status, "to": d.to_address,
                              "subject": d.subject, "body": d.body, "due_at": d.due_at.isoformat() if d.due_at else None}
                             for d in db.scalars(select(FollowUpDraft).where(FollowUpDraft.user_id == user.id))],
        "interview_prep": [{"application_id": str(p.application_id), "questions": p.questions, "notes": p.notes, "completed_at": p.completed_at.isoformat() if p.completed_at else None}
                            for p in db.scalars(select(InterviewPrep).where(InterviewPrep.user_id == user.id))],
        "calendar_events": [{"id": str(e.id), "application_id": str(e.application_id) if e.application_id else None, "title": e.title, "starts_at": e.starts_at.isoformat(), "ends_at": e.ends_at.isoformat() if e.ends_at else None, "location": e.location}
                             for e in db.scalars(select(CalendarEvent).where(CalendarEvent.user_id == user.id))],
        "send_log": [{"recipient": s.recipient, "success": s.success, "at": s.created_at.isoformat()} for s in db.scalars(select(SendLog).where(SendLog.user_id == user.id))],
        "audit_log": [{"action": a.action, "at": a.created_at.isoformat()} for a in db.scalars(select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.created_at))],
    }
    audit(db, user.id, "privacy.export", request=request)
    db.commit()
    return Response(json.dumps(data, indent=2, ensure_ascii=False, default=str), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="jobapply-export.json"', "Cache-Control": "no-store"})


@router.get("/privacy/audit-log")
def my_audit_log(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.created_at.desc()).limit(200)).all()
    return [{"action": r.action, "entity_type": r.entity_type, "at": r.created_at.isoformat(), "ip": r.ip} for r in rows]


@router.put("/privacy/ai-training")
def ai_training(body: TrainingOptIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.ai_training_opt_in = body.opt_in
    audit(db, user.id, "privacy.ai_training", request=request, opt_in=body.opt_in)
    db.commit()
    return {"ai_training_opt_in": user.ai_training_opt_in}


@router.delete("/privacy/application-history", status_code=204)
def delete_history(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deletes applications, generated documents, emails, events and send logs. Jobs and the profile are kept."""
    for a in db.scalars(select(Application).where(Application.user_id == user.id)):
        db.delete(a)
    db.flush()
    get_storage().delete_prefix(f"u/{user.id}/docs")
    for v in db.scalars(select(ResumeVersion).where(ResumeVersion.user_id == user.id)):
        db.delete(v)
    for s in db.scalars(select(SendLog).where(SendLog.user_id == user.id)):
        db.delete(s)
    for m in db.scalars(select(IncomingMessage).where(IncomingMessage.user_id == user.id)):
        db.delete(m)
    for d in db.scalars(select(FollowUpDraft).where(FollowUpDraft.user_id == user.id)):
        db.delete(d)
    for r in db.scalars(select(FollowUpRule).where(FollowUpRule.user_id == user.id)):
        db.delete(r)
    for p in db.scalars(select(InterviewPrep).where(InterviewPrep.user_id == user.id)):
        db.delete(p)
    for e in db.scalars(select(CalendarEvent).where(CalendarEvent.user_id == user.id)):
        db.delete(e)
    audit(db, user.id, "privacy.delete_history", request=request)
    db.commit()


@router.delete("/privacy/account", status_code=204)
def delete_account(body: DeleteAccountIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Permanently deletes the account and ALL associated data, including stored files."""
    if user.password_hash and not (body.password and verify_password(body.password, user.password_hash)):
        raise HTTPException(403, "Password confirmation failed.")
    uid = user.id
    get_storage().delete_prefix(f"u/{uid}")
    db.delete(user)
    audit(db, None, "account.deleted", request=request, user_ref=str(uid)[:8])
    db.commit()
