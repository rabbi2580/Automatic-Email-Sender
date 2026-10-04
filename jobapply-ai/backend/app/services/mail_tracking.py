"""Opt-in, metadata-only reply tracking for connected Gmail/Outlook accounts."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_str
from app.models import Application, ApplicationEmail, ApplicationEvent, EmailAccount, IncomingMessage, Job, Notification, User
from app.models.base import utcnow
from app.services.delivery import oauth
from app.services.workflow import transition

READ_SCOPES = {"https://www.googleapis.com/auth/gmail.readonly", "Mail.ReadBasic"}


def classify_message(subject: str, snippet: str) -> str:
    text = f"{subject} {snippet}".lower()
    if any(x in text for x in ("delivery status notification", "mail delivery failed", "undeliverable", "delivery incomplete", "address not found", "returned mail")):
        return "bounce"
    if any(x in text for x in ("complaint", "abuse report", "do not contact", "unsubscribe")):
        return "complaint"
    if any(x in text for x in ("out of office", "automatic reply", "auto-reply", "away from the office", "vacation responder")):
        return "auto_reply"
    if any(x in text for x in ("interview", "phone screen", "technical assessment", "meet with", "schedule a call")):
        return "interview"
    if any(x in text for x in ("reject", "not moving forward", "unfortunately", "other candidates", "position has been filled")):
        return "rejection"
    return "reply"


def _clean(value: str | None, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _subject_key(value: str | None) -> str:
    return re.sub(r"^(?:re|fwd|fw|following up)\s*:\s*", "", _clean(value, 500), flags=re.I).strip().lower()


def _gmail_messages(token: str, addresses: list[str], after: datetime) -> list[dict]:
    if not addresses:
        return []
    clauses = " ".join(f"from:{a}" for a in addresses[:25])
    q = f"after:{int(after.timestamp())} {{{clauses}}}"
    headers = {"Authorization": f"Bearer {token}"}
    r = httpx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", params={"q": q, "maxResults": 50}, headers=headers, timeout=30)
    r.raise_for_status()
    out = []
    for item in r.json().get("messages", []):
        detail = httpx.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{item['id']}", params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]}, headers=headers, timeout=30)
        detail.raise_for_status(); data = detail.json(); headers_by_name = {h.get("name", "").lower(): h.get("value", "") for h in data.get("payload", {}).get("headers", [])}
        out.append({"external_id": item["id"], "thread_id": data.get("threadId", ""), "from": headers_by_name.get("from", "").split("<")[-1].rstrip("> "),
                    "subject": headers_by_name.get("subject", ""), "snippet": data.get("snippet", ""), "received_at": headers_by_name.get("date")})
    return out


def _outlook_messages(token: str, addresses: list[str], after: datetime) -> list[dict]:
    if not addresses:
        return []
    sender_filter = " or ".join(f"from/emailAddress/address eq '{a.replace(chr(39), chr(39) * 2)}'" for a in addresses[:25])
    date_filter = f"receivedDateTime ge {after.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')}"
    r = httpx.get("https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages", params={"$select": "id,conversationId,from,subject,bodyPreview,receivedDateTime", "$filter": f"({sender_filter}) and {date_filter}", "$top": "50"}, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status(); out = []
    allowed = {a.lower() for a in addresses}
    for data in r.json().get("value", []):
        sender = (((data.get("from") or {}).get("emailAddress") or {}).get("address") or "").lower()
        if sender not in allowed:
            continue
        out.append({"external_id": data.get("id", ""), "thread_id": data.get("conversationId", ""), "from": sender,
                    "subject": data.get("subject", ""), "snippet": data.get("bodyPreview", ""), "received_at": data.get("receivedDateTime")})
    return out


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _update_application(db: Session, app: Application, classification: str, incoming_id: str) -> bool:
    if classification not in {"interview", "rejection", "reply"}:
        return False
    target = "interview" if classification == "interview" else "rejected" if classification == "rejection" else "application_confirmed"
    if app.status not in {"sent", "application_confirmed", "interview"} or (app.status == target):
        return False
    old = app.status
    transition(db, app, target, actor="system", detail={"auto_updated": True, "source": "mailbox", "incoming_message_id": incoming_id})
    db.add(Notification(user_id=app.user_id, kind="application_update", title=f"Application update: {target.replace('_', ' ')}",
                        body="A new mailbox message changed this application status. You can undo the automatic update.", entity_type="application", entity_id=str(app.id)))
    return old != target


def poll_account(db: Session, account: EmailAccount) -> int:
    if not account.tracking_enabled or account.status != "active" or not READ_SCOPES.intersection(set(account.scopes or [])):
        return 0
    user = db.get(User, account.user_id)
    after = account.last_tracking_at or (utcnow() - timedelta(days=30))
    apps = db.execute(select(Application, ApplicationEmail).join(ApplicationEmail, ApplicationEmail.application_id == Application.id)
                      .where(Application.user_id == user.id, ApplicationEmail.email_account_id == account.id,
                             Application.deleted_at.is_(None), ApplicationEmail.status == "sent")).all()
    addresses = [e.to_address for _, e in apps if e.to_address]
    creds = json.loads(decrypt_str(account.encrypted_credentials))
    token = oauth.access_token(account.provider, creds, tracking=True)
    messages = _gmail_messages(token, addresses, after) if account.provider == "gmail" else _outlook_messages(token, addresses, after)
    handled = 0
    for msg in messages:
        if not msg.get("external_id") or db.scalar(select(IncomingMessage.id).where(IncomingMessage.user_id == user.id, IncomingMessage.provider == account.provider, IncomingMessage.external_id == msg["external_id"])):
            continue
        classification = classify_message(msg.get("subject", ""), msg.get("snippet", ""))
        candidates = [(a, e) for a, e in apps if e.to_address.lower() == msg.get("from", "").lower()]
        # Recipient matching is mandatory; subject/thread matching disambiguates multiple applications to one recruiter.
        keyed = [pair for pair in candidates if _subject_key(pair[1].subject) == _subject_key(msg.get("subject"))]
        matching = keyed[0] if keyed else candidates[0] if len(candidates) == 1 else None
        app = matching[0] if matching else None
        incoming = IncomingMessage(user_id=user.id, email_account_id=account.id, application_id=app.id if app else None,
                                   provider=account.provider, external_id=msg["external_id"], thread_id=msg.get("thread_id", ""),
                                   from_address=_clean(msg.get("from"), 320), subject=_clean(msg.get("subject")), received_at=_parse_dt(msg.get("received_at")),
                                   classification=classification, snippet=_clean(msg.get("snippet")), auto_updated=False)
        db.add(incoming); db.flush()
        if app:
            incoming.auto_updated = _update_application(db, app, classification, str(incoming.id))
        handled += 1
    account.last_tracking_at, account.tracking_error = utcnow(), None
    db.commit()
    return handled


def poll_mailboxes(db: Session) -> int:
    total = 0
    for account in db.scalars(select(EmailAccount).where(EmailAccount.tracking_enabled.is_(True), EmailAccount.deleted_at.is_(None))).all():
        try:
            total += poll_account(db, account)
        except Exception as exc:  # noqa: BLE001
            account.last_tracking_at, account.tracking_error = utcnow(), f"Mailbox sync failed ({type(exc).__name__})."
            db.commit()
    return total
