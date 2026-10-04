from __future__ import annotations

import json
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.helpers import account_out
from app.core.config import get_settings
from app.core.crypto import decrypt_str, encrypt_str, sign_payload, verify_payload
from app.core.db import get_db
from app.core.deps import get_current_user, get_owned
from app.models import EmailAccount, User
from app.models.base import utcnow
from app.schemas.api import EmailConnectIn, SmtpConnectIn
from app.services.audit import audit
from app.services.delivery import oauth
from app.services.delivery.base import DeliveryError
from app.services.delivery.registry import get_channel
from app.services.parsing.url_fetch import _is_public_ip

router = APIRouter(prefix="/integrations/email", tags=["email"])


def _save_account(db: Session, user: User, provider: str, address: str, display: str, creds: dict, scopes: list[str]) -> EmailAccount:
    acct = db.scalar(select(EmailAccount).where(EmailAccount.user_id == user.id, EmailAccount.provider == provider, EmailAccount.address == address))
    if acct:
        acct.deleted_at, acct.status = None, "active"
    else:
        acct = EmailAccount(user_id=user.id, provider=provider, address=address, encrypted_credentials="", scopes=scopes)
        db.add(acct)
    acct.display_name, acct.scopes, acct.consent_given_at = display or user.full_name, scopes, utcnow()
    acct.encrypted_credentials = encrypt_str(json.dumps(creds))
    others = db.scalar(select(EmailAccount.id).where(EmailAccount.user_id == user.id, EmailAccount.deleted_at.is_(None), EmailAccount.id != acct.id))
    acct.is_default = acct.is_default or others is None
    db.flush()
    return acct


@router.get("")
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(EmailAccount).where(EmailAccount.user_id == user.id, EmailAccount.deleted_at.is_(None)).order_by(EmailAccount.created_at)).all()
    return [account_out(a) for a in rows]


@router.post("/connect")
def connect(body: EmailConnectIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.consent:
        raise HTTPException(422, "Please confirm that you allow JobApply AI to send emails from your account on your behalf, only after you approve each application.")
    tracking = bool(body.tracking or (user.settings or {}).get("mailbox_tracking"))
    state = sign_payload({"u": str(user.id), "p": body.provider, "tracking": tracking}, 600, "email_oauth")
    try:
        url = oauth.authorization_url(body.provider, state, tracking=tracking)
    except DeliveryError as e:
        raise HTTPException(501, e.reason)
    audit(db, user.id, "email.connect_start", request=request, provider=body.provider)
    db.commit()
    return {"authorization_url": url}


@router.get("/callback/{provider}")
def callback(provider: str, code: str, state: str, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    st = verify_payload(state, "email_oauth")
    if not st or st["p"] != provider:
        raise HTTPException(400, "Invalid or expired connection request.")
    user = db.get(User, uuid.UUID(st["u"]))
    if not user:
        raise HTTPException(400, "Invalid connection request.")
    try:
        tracking = bool(st.get("tracking"))
        tok = oauth.exchange_code(provider, code, tracking=tracking)
        if not tok.get("refresh_token"):
            raise DeliveryError("The provider did not grant offline access. Remove the app from your account permissions and connect again.")
        if provider == "gmail":
            r = httpx.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=20)
            r.raise_for_status()
            address, display = r.json()["email"], r.json().get("name", "")
            scopes = oauth.scopes_for("gmail", tracking)
        else:
            r = httpx.get("https://graph.microsoft.com/v1.0/me", headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=20)
            r.raise_for_status()
            j = r.json()
            address, display = j.get("mail") or j["userPrincipalName"], j.get("displayName", "")
            scopes = oauth.scopes_for("outlook", tracking)
    except (DeliveryError, httpx.HTTPError, KeyError) as e:
        return RedirectResponse(f"{s.public_base_url}/email?error=connect_failed")
    acct = _save_account(db, user, provider, address.lower(), display, {"refresh_token": tok["refresh_token"]}, scopes)
    acct.tracking_enabled = tracking
    audit(db, user.id, "email.connected", request=request, provider=provider)
    db.commit()
    return RedirectResponse(f"{s.public_base_url}/email?connected={provider}")


@router.post("/smtp", status_code=201)
def connect_smtp(body: SmtpConnectIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.consent:
        raise HTTPException(422, "Please confirm you allow sending from this account after your approval.")
    s = get_settings()
    if s.environment not in ("development", "test"):
        import socket

        try:
            infos = socket.getaddrinfo(body.host, body.port, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            raise HTTPException(422, "The SMTP host could not be resolved.")
        if not all(_is_public_ip(i[4][0]) for i in infos):
            raise HTTPException(422, "That SMTP host is not allowed.")
    creds = {"host": body.host, "port": body.port, "username": body.username, "password": body.password, "security": body.security}
    try:
        get_channel("smtp").verify(creds)
    except DeliveryError as e:
        raise HTTPException(422, e.reason)
    acct = _save_account(db, user, "smtp", body.address.lower(), body.display_name, creds, ["smtp"])
    audit(db, user.id, "email.connected", request=request, provider="smtp")
    db.commit()
    return account_out(acct)


@router.post("/{account_id}/default")
def make_default(account_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = get_owned(db, EmailAccount, account_id, user)
    for x in db.scalars(select(EmailAccount).where(EmailAccount.user_id == user.id)):
        x.is_default = x.id == a.id
    db.commit()
    return account_out(a)


@router.delete("/{account_id}", status_code=204)
def disconnect(account_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deletes stored credentials and revokes the grant at the provider (best effort)."""
    a = get_owned(db, EmailAccount, account_id, user)
    try:
        creds = json.loads(decrypt_str(a.encrypted_credentials))
        if a.provider == "gmail" and creds.get("refresh_token"):
            httpx.post("https://oauth2.googleapis.com/revoke", data={"token": creds["refresh_token"]}, timeout=10)
    except Exception:  # noqa: BLE001 - revocation is best effort; credentials are deleted regardless
        pass
    a.encrypted_credentials, a.status, a.deleted_at, a.is_default = "", "revoked", utcnow(), False
    audit(db, user.id, "email.disconnected", request=request, provider=a.provider)
    db.commit()
