"""Approval + sending orchestration. The only code path that can send an application.

Safeguards enforced here (not in the UI):
  1. application must be `approved` by the user and pass QC;
  2. approved content hash must equal the current content (edits after approval invalidate approval);
  3. a signed confirmation token, bound to the exact recipients/subjects/attachments previewed, must be presented;
  4. per-user hourly/daily caps, plan quota, verified email, duplicate-send protection (idempotency key);
  5. every attempt is logged (send_logs, application_events, audit_logs).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import decrypt_str, sign_payload, verify_payload
from app.models import Application, ApplicationDocument, ApplicationEmail, EmailAccount, FollowUpDraft, Job, SendLog, User
from app.models.base import utcnow
from app.services import usage
from app.services.audit import audit
from app.services.delivery.base import Attachment, DeliveryError, OutgoingEmail
from app.services.delivery.registry import get_channel
from app.services.pipeline import email_content_hash, run_application_qc
from app.services.storage import get_storage
from app.services.workflow import transition

log = logging.getLogger("jobapply.delivery")
RETRY_DELAYS = (0.5, 2.0)


class SendBlocked(Exception):
    def __init__(self, message: str, code: str = "blocked"):
        super().__init__(message)
        self.message, self.code = message, code


def _load(db: Session, user: User, app_id: uuid.UUID):
    app = db.get(Application, app_id)
    if not app or app.user_id != user.id or app.deleted_at is not None:
        raise SendBlocked("Application not found.", "not_found")
    return app, db.get(Job, app.job_id), db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == app.id))


def _docs(db: Session, em: ApplicationEmail) -> list[ApplicationDocument]:
    ids = [uuid.UUID(i) for i in (em.attachment_doc_ids or [])]
    return list(db.scalars(select(ApplicationDocument).where(ApplicationDocument.id.in_(ids)))) if ids else []


def current_hash(db: Session, em: ApplicationEmail) -> str:
    return email_content_hash(em.to_address, em.subject, em.body, [{"sha256": d.sha256} for d in _docs(db, em)])


def approve_application(db: Session, user: User, app: Application) -> Application:
    if app.status not in ("awaiting_review", "approved"):
        raise SendBlocked(f"An application in status '{app.status}' cannot be approved.")
    report = run_application_qc(db, app, commit=False)
    if not report["passed"]:
        db.commit()
        raise SendBlocked(report["summary"], "qc_failed")
    em = db.scalar(select(ApplicationEmail).where(ApplicationEmail.application_id == app.id))
    if em is None:
        raise SendBlocked("The application has no email draft.")
    app.content_hash = current_hash(db, em)
    app.approved_at = utcnow()
    transition(db, app, "approved", actor="user")
    audit(db, user.id, "application.approve", entity_type="application", entity_id=app.id)
    db.commit()
    return app


def _window_count(db: Session, user_id: uuid.UUID, delta: timedelta) -> int:
    return int(db.scalar(select(func.count()).select_from(SendLog).where(SendLog.user_id == user_id, SendLog.success.is_(True),
                                                                          SendLog.created_at >= datetime.now(timezone.utc) - delta)) or 0)


def preview_send(db: Session, user: User, app_ids: list[uuid.UUID]) -> dict:
    s = get_settings()
    items, hashes, ok_ids = [], {}, []
    for aid in app_ids:
        try:
            app, job, em = _load(db, user, aid)
        except SendBlocked as e:
            items.append({"application_id": str(aid), "blocked": True, "problems": [e.message]})
            continue
        problems: list[str] = []
        if app.status != "approved":
            problems.append("Not approved yet.")
        if not app.qc_passed:
            problems.append("Quality checks have not passed.")
        if not em or not em.to_address:
            problems.append("This job has no application email. Use the application link instead.")
        acct = db.get(EmailAccount, em.email_account_id) if em and em.email_account_id else None
        if not acct or acct.status != "active" or acct.deleted_at is not None:
            problems.append("Connect an email account to send.")
        docs = _docs(db, em) if em else []
        if em and app.status == "approved" and current_hash(db, em) != app.content_hash:
            problems.append("The content changed after approval. Review and approve again.")
        items.append({"application_id": str(app.id), "company": job.company_name, "position": job.job_title, "from": acct.address if acct else None,
                      "to": em.to_address if em else None, "subject": em.subject if em else None,
                      "attachments": [{"filename": d.filename, "size_bytes": d.size_bytes} for d in docs], "blocked": bool(problems), "problems": problems})
        if not problems:
            hashes[str(app.id)] = app.content_hash
            ok_ids.append(str(app.id))
    sendable = [i for i in items if not i["blocked"]]
    token = sign_payload({"u": str(user.id), "h": hashes}, s.confirmation_token_minutes * 60, "send") if sendable else None
    return {"count": len(sendable), "items": items, "confirmation_token": token,
            "limits": {"hour_remaining": max(0, s.email_send_per_hour - _window_count(db, user.id, timedelta(hours=1))),
                       "day_remaining": max(0, s.email_send_per_day - _window_count(db, user.id, timedelta(days=1)))},
            "notice": f"You are about to send {len(sendable)} application(s). Each will include the attachments listed. Nothing is sent until you confirm."}


def _send_with_retry(channel, creds: dict, msg: OutgoingEmail) -> str | None:
    last: DeliveryError | None = None
    for i in range(len(RETRY_DELAYS) + 1):
        try:
            return channel.send(creds, msg)
        except DeliveryError as e:
            last = e
            if not e.retryable or i == len(RETRY_DELAYS):
                break
            time.sleep(RETRY_DELAYS[i])
    assert last is not None
    raise last


def send_applications(db: Session, user: User, app_ids: list[uuid.UUID], token: str, request=None) -> list[dict]:
    s = get_settings()
    body = verify_payload(token or "", "send")
    if not body or body.get("u") != str(user.id):
        raise SendBlocked("The confirmation expired or is invalid. Please review and confirm again.", "bad_confirmation")
    approved_hashes: dict = body["h"]
    if set(approved_hashes) != {str(i) for i in app_ids}:
        raise SendBlocked("The selection changed since you confirmed. Please review and confirm again.", "selection_changed")
    if s.require_verified_email_to_send and not user.email_verified:
        raise SendBlocked("Please verify your email address before sending applications.", "email_unverified")
    if user.flagged_reason:
        raise SendBlocked("Sending is paused on your account. Contact support.", "account_flagged")

    results = []
    for aid in app_ids:
        res = {"application_id": str(aid), "status": "failed", "message": ""}
        try:
            app, job, em = _load(db, user, aid)
            if app.status != "approved" or not app.qc_passed:
                raise SendBlocked("Application is not approved.")
            if current_hash(db, em) != approved_hashes[str(aid)] or app.content_hash != approved_hashes[str(aid)]:
                raise SendBlocked("The content changed after approval. Approve again.", "content_changed")
            if _window_count(db, user.id, timedelta(hours=1)) >= s.email_send_per_hour:
                raise SendBlocked("Hourly sending limit reached. Try again later.", "rate_limited")
            if _window_count(db, user.id, timedelta(days=1)) >= s.email_send_per_day:
                raise SendBlocked("Daily sending limit reached. Try again tomorrow.", "rate_limited")
            usage.check_quota(db, user, "emails_sent", 1)
            idem = hashlib.sha256(f"{app.id}:{app.content_hash}".encode()).hexdigest()
            locked = db.execute(select(ApplicationEmail).where(ApplicationEmail.id == em.id).with_for_update()).scalar_one()
            if locked.status in ("sent", "sending") or db.scalar(select(ApplicationEmail.id).where(ApplicationEmail.idempotency_key == idem)):
                res.update(status="skipped", message="Already sent.")
                results.append(res)
                continue
            acct = db.get(EmailAccount, em.email_account_id)
            if not acct or acct.status != "active":
                raise SendBlocked("Your email account needs to be reconnected.")
            locked.status, locked.idempotency_key, locked.attempts = "sending", idem, locked.attempts + 1
            db.commit()
            creds = json.loads(decrypt_str(acct.encrypted_credentials))
            msg = OutgoingEmail(from_address=acct.address, from_name=acct.display_name, to=em.to_address, subject=em.subject, body=em.body,
                                attachments=[Attachment(d.filename, d.content_type, get_storage().get(d.storage_key)) for d in _docs(db, em)])
            try:
                mid = _send_with_retry(get_channel(acct.provider), creds, msg)
            except DeliveryError as de:
                locked.status, locked.last_error, locked.idempotency_key = "failed", de.reason[:500], None
                if de.needs_reauth:
                    acct.status = "needs_reauth"
                db.add(SendLog(user_id=user.id, application_id=app.id, provider=acct.provider, recipient=em.to_address, success=False, error=de.reason[:500]))
                audit(db, user.id, "application.send_failed", entity_type="application", entity_id=app.id, provider=acct.provider, retryable=de.retryable)
                db.commit()
                res.update(status="failed", message=de.reason)
                results.append(res)
                continue
            now = utcnow()
            locked.status, locked.sent_at, locked.provider_message_id, locked.last_error = "sent", now, mid, None
            app.sent_at, app.channel = now, "email"
            acct.last_used_at = now
            transition(db, app, "sent", actor="system", detail={"to": em.to_address, "provider": acct.provider})
            db.add(SendLog(user_id=user.id, application_id=app.id, provider=acct.provider, recipient=em.to_address, success=True))
            usage.record_usage(db, user.id, "emails_sent", 1, application_id=str(app.id))
            audit(db, user.id, "application.sent", entity_type="application", entity_id=app.id, provider=acct.provider, request=request)
            db.commit()
            res.update(status="sent", message="Sent.")
        except SendBlocked as e:
            db.rollback()
            res.update(status="blocked", message=e.message)
        except Exception as e:  # noqa: BLE001 - HTTPException(quota) and unexpected errors must not abort the whole batch
            db.rollback()
            detail = getattr(e, "detail", None)
            res.update(status="blocked" if detail else "failed", message=(detail.get("message") if isinstance(detail, dict) else str(detail)) if detail else f"Unexpected error ({type(e).__name__}).")
            if not detail:
                log.exception("send failed")
        results.append(res)
    return results


def preview_followup(db: Session, user: User, draft_id: uuid.UUID) -> dict:
    draft = db.get(FollowUpDraft, draft_id)
    if not draft or draft.user_id != user.id:
        raise SendBlocked("Follow-up not found.", "not_found")
    app, job, em = _load(db, user, draft.application_id)
    problems = []
    if draft.status != "approved": problems.append("Approve the follow-up first.")
    if draft.needs_input or not draft.body.strip(): problems.append("Complete the follow-up first.")
    if app.status not in {"sent", "application_confirmed", "interview"}: problems.append("The application is not eligible for a follow-up.")
    acct = db.get(EmailAccount, em.email_account_id) if em and em.email_account_id else None
    if not acct or acct.status != "active": problems.append("Reconnect the sending email account.")
    return {"follow_up_id": str(draft.id), "application_id": str(app.id), "company": job.company_name, "position": job.job_title,
            "from": acct.address if acct else None, "to": draft.to_address, "subject": draft.subject, "body": draft.body,
            "blocked": bool(problems), "problems": problems}


def send_followup(db: Session, user: User, draft_id: uuid.UUID, request=None) -> dict:
    s = get_settings()
    draft = db.execute(select(FollowUpDraft).where(FollowUpDraft.id == draft_id, FollowUpDraft.user_id == user.id).with_for_update()).scalar_one_or_none()
    if not draft: raise SendBlocked("Follow-up not found.", "not_found")
    if draft.status == "sent": return {"follow_up_id": str(draft.id), "status": "skipped", "message": "Already sent."}
    if draft.status != "approved": raise SendBlocked("Approve the follow-up before sending.")
    app, job, em = _load(db, user, draft.application_id)
    if app.status not in {"sent", "application_confirmed", "interview"}: raise SendBlocked("Application is not eligible for a follow-up.")
    if _window_count(db, user.id, timedelta(hours=1)) >= s.email_send_per_hour or _window_count(db, user.id, timedelta(days=1)) >= s.email_send_per_day:
        raise SendBlocked("Sending limit reached. Try again later.", "rate_limited")
    usage.check_quota(db, user, "emails_sent", 1)
    acct = db.get(EmailAccount, em.email_account_id) if em else None
    if not acct or acct.status != "active": raise SendBlocked("Your email account needs to be reconnected.")
    idem = hashlib.sha256(f"followup:{draft.id}:{draft.content_hash}".encode()).hexdigest()
    if db.scalar(select(FollowUpDraft.id).where(FollowUpDraft.idempotency_key == idem)):
        return {"follow_up_id": str(draft.id), "status": "skipped", "message": "Already sent."}
    draft.idempotency_key = idem
    db.commit()
    try:
        creds = json.loads(decrypt_str(acct.encrypted_credentials))
        mid = _send_with_retry(get_channel(acct.provider), creds, OutgoingEmail(from_address=acct.address, from_name=acct.display_name,
                     to=draft.to_address, subject=draft.subject, body=draft.body, attachments=[]))
    except DeliveryError as de:
        draft.idempotency_key = None
        if de.needs_reauth: acct.status = "needs_reauth"
        db.add(SendLog(user_id=user.id, application_id=app.id, provider=acct.provider, recipient=draft.to_address, success=False, error=de.reason[:500]))
        db.commit()
        return {"follow_up_id": str(draft.id), "status": "failed", "message": de.reason}
    draft.status, draft.sent_at, draft.provider_message_id = "sent", utcnow(), mid
    db.add(SendLog(user_id=user.id, application_id=app.id, provider=acct.provider, recipient=draft.to_address, success=True))
    usage.record_usage(db, user.id, "emails_sent", 1, application_id=str(app.id))
    audit(db, user.id, "follow_up.sent", entity_type="application", entity_id=app.id, provider=acct.provider, request=request)
    db.commit()
    return {"follow_up_id": str(draft.id), "status": "sent", "message": "Sent."}


def mark_applied_manually(db: Session, user: User, app: Application) -> Application:
    """For URL-based applications: the user applied themselves on the employer site."""
    if app.status not in ("awaiting_review", "approved", "cv_generated"):
        raise SendBlocked("This application cannot be marked as applied from its current status.")
    app.sent_at, app.channel = utcnow(), "url_assisted"
    transition(db, app, "sent", actor="user", force=True, detail={"manual": True})
    audit(db, user.id, "application.marked_applied", entity_type="application", entity_id=app.id)
    db.commit()
    return app
