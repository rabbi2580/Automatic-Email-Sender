"""OAuth helpers for Gmail (send scope only) and Outlook / Microsoft Graph (Mail.Send only)."""
from __future__ import annotations

from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.services.delivery.base import DeliveryChannel, DeliveryError, OutgoingEmail, build_mime

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GMAIL_SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send", "openid", "email", "profile"]
MS_SCOPES = ["offline_access", "Mail.Send", "User.Read"]


def ms_endpoints() -> tuple[str, str]:
    t = get_settings().microsoft_tenant
    base = f"https://login.microsoftonline.com/{t}/oauth2/v2.0"
    return f"{base}/authorize", f"{base}/token"


def redirect_uri(provider: str) -> str:
    return f"{get_settings().api_base_url}/api/v1/integrations/email/callback/{provider}"


def authorization_url(provider: str, state: str) -> str:
    s = get_settings()
    if provider == "gmail":
        if not s.google_client_id:
            raise DeliveryError("Google OAuth is not configured on this server.")
        q = {"client_id": s.google_client_id, "redirect_uri": redirect_uri("gmail"), "response_type": "code", "scope": " ".join(GMAIL_SCOPES),
             "access_type": "offline", "prompt": "consent", "state": state, "include_granted_scopes": "true"}
        return f"{GOOGLE_AUTH}?{urlencode(q)}"
    if provider == "outlook":
        if not s.microsoft_client_id:
            raise DeliveryError("Microsoft OAuth is not configured on this server.")
        auth, _ = ms_endpoints()
        q = {"client_id": s.microsoft_client_id, "redirect_uri": redirect_uri("outlook"), "response_type": "code", "scope": " ".join(MS_SCOPES),
             "state": state, "response_mode": "query", "prompt": "consent"}
        return f"{auth}?{urlencode(q)}"
    raise DeliveryError("Unknown provider")


def exchange_code(provider: str, code: str) -> dict:
    s = get_settings()
    if provider == "gmail":
        url, data = GOOGLE_TOKEN, {"code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                                   "redirect_uri": redirect_uri("gmail"), "grant_type": "authorization_code"}
    else:
        url = ms_endpoints()[1]
        data = {"code": code, "client_id": s.microsoft_client_id, "client_secret": s.microsoft_client_secret, "redirect_uri": redirect_uri("outlook"),
                "grant_type": "authorization_code", "scope": " ".join(MS_SCOPES)}
    try:
        r = httpx.post(url, data=data, timeout=20)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as exc:
        raise DeliveryError(f"Could not complete sign-in ({type(exc).__name__}).") from exc


def _refresh(provider: str, creds: dict) -> str:
    s = get_settings()
    if provider == "gmail":
        url, data = GOOGLE_TOKEN, {"client_id": s.google_client_id, "client_secret": s.google_client_secret, "refresh_token": creds["refresh_token"], "grant_type": "refresh_token"}
    else:
        url = ms_endpoints()[1]
        data = {"client_id": s.microsoft_client_id, "client_secret": s.microsoft_client_secret, "refresh_token": creds["refresh_token"], "grant_type": "refresh_token", "scope": " ".join(MS_SCOPES)}
    try:
        r = httpx.post(url, data=data, timeout=20)
    except httpx.HTTPError as exc:
        raise DeliveryError("Could not reach the email provider.", retryable=True) from exc
    if r.status_code in (400, 401):
        raise DeliveryError("Your email connection has expired. Please reconnect your account.", needs_reauth=True)
    if r.status_code >= 500:
        raise DeliveryError("The email provider is temporarily unavailable.", retryable=True)
    r.raise_for_status()
    return r.json()["access_token"]


class GmailChannel(DeliveryChannel):
    name = "gmail"

    def send(self, credentials, message: OutgoingEmail):
        import base64

        token = _refresh("gmail", credentials)
        raw = base64.urlsafe_b64encode(build_mime(message).as_bytes()).decode()
        try:
            r = httpx.post(GMAIL_SEND, json={"raw": raw}, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        except httpx.HTTPError as exc:
            raise DeliveryError("Could not reach Gmail.", retryable=True) from exc
        if r.status_code in (401, 403):
            raise DeliveryError("Gmail rejected the request. Please reconnect your account.", needs_reauth=True)
        if r.status_code == 429 or r.status_code >= 500:
            raise DeliveryError("Gmail is rate-limiting or unavailable.", retryable=True)
        if r.status_code >= 400:
            raise DeliveryError(f"Gmail returned an error ({r.status_code}).")
        return r.json().get("id")


class OutlookChannel(DeliveryChannel):
    name = "outlook"

    def send(self, credentials, message: OutgoingEmail):
        import base64

        token = _refresh("outlook", credentials)
        payload = {"message": {
            "subject": message.subject, "body": {"contentType": "Text", "content": message.body},
            "toRecipients": [{"emailAddress": {"address": message.to}}],
            "attachments": [{"@odata.type": "#microsoft.graph.fileAttachment", "name": a.filename, "contentType": a.content_type,
                             "contentBytes": base64.b64encode(a.data).decode()} for a in message.attachments]},
            "saveToSentItems": True}
        try:
            r = httpx.post("https://graph.microsoft.com/v1.0/me/sendMail", json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        except httpx.HTTPError as exc:
            raise DeliveryError("Could not reach Outlook.", retryable=True) from exc
        if r.status_code in (401, 403):
            raise DeliveryError("Outlook rejected the request. Please reconnect your account.", needs_reauth=True)
        if r.status_code == 429 or r.status_code >= 500:
            raise DeliveryError("Outlook is rate-limiting or unavailable.", retryable=True)
        if r.status_code >= 400:
            raise DeliveryError(f"Outlook returned an error ({r.status_code}).")
        return None  # Graph sendMail returns 202 with no id
