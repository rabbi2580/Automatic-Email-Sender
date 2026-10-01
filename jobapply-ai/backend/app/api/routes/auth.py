from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import sign_payload, verify_payload
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.ratelimit import client_ip, limiter, rate_limit
from app.core.security import create_access_token, hash_password, needs_rehash, new_refresh_token, validate_password_strength, verify_password
from app.models import Profile, RefreshToken, Subscription, User
from app.models.base import utcnow
from app.schemas.api import ForgotPasswordIn, LoginIn, PasswordChangeIn, RefreshIn, RegisterIn, ResetPasswordIn, TokenOut, UserOut, UserPatch, VerifyEmailIn
from app.services.audit import audit
from app.services.mailer import send_system_email

router = APIRouter(prefix="/auth", tags=["auth"])
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def issue_tokens(db: Session, user: User, family: str | None = None) -> TokenOut:
    s = get_settings()
    raw = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=_sha(raw), family_id=family or str(uuid.uuid4()),
                        expires_at=utcnow() + timedelta(days=s.refresh_token_days)))
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, user.role), refresh_token=raw, expires_in=s.access_token_minutes * 60)


@router.post("/register", status_code=201, dependencies=[Depends(rate_limit("auth", get_settings().auth_rate_limit_per_minute))])
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if not body.accept_terms:
        raise HTTPException(422, "You must accept the Terms of Service and Privacy Policy.")
    problem = validate_password_strength(body.password)
    if problem:
        raise HTTPException(422, problem)
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists.")
    token = secrets.token_urlsafe(32)
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name, locale=body.locale, verification_token_hash=_sha(token),
                consent_terms_at=utcnow(), consent_ai_disclosure_at=utcnow())
    db.add(user)
    db.flush()
    db.add(Subscription(user_id=user.id, plan="free"))
    db.add(Profile(user_id=user.id, full_name=body.full_name, email=email))
    audit(db, user.id, "auth.register", entity_type="user", entity_id=user.id, request=request)
    db.commit()
    s = get_settings()
    send_system_email(email, "Verify your JobApply AI email", f"Welcome! Verify your email: {s.public_base_url}/verify-email?token={token}")
    out = {"id": str(user.id), "email": email, "message": "Account created. Please verify your email."}
    if s.environment in ("development", "test"):
        out["dev_verification_token"] = token
    return out


@router.post("/verify-email")
def verify_email(body: VerifyEmailIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.verification_token_hash == _sha(body.token)))
    if not user:
        raise HTTPException(400, "Invalid or expired verification link.")
    user.email_verified, user.verification_token_hash = True, None
    db.commit()
    return {"verified": True}


@router.post("/resend-verification", dependencies=[Depends(rate_limit("resend", 3))])
def resend_verification(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.email_verified:
        return {"verified": True}
    token = secrets.token_urlsafe(32)
    user.verification_token_hash = _sha(token)
    db.commit()
    s = get_settings()
    send_system_email(user.email, "Verify your JobApply AI email", f"Verify your email: {s.public_base_url}/verify-email?token={token}")
    return {"sent": True, **({"dev_verification_token": token} if s.environment in ("development", "test") else {})}


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    out = {"sent": True}
    if not user or user.deleted_at or not user.is_active:
        return out
    token = secrets.token_urlsafe(32)
    user.password_reset_token_hash = _sha(token)
    user.password_reset_expires_at = utcnow() + timedelta(hours=1)
    audit(db, user.id, "auth.password_reset_requested", request=request)
    db.commit()
    s = get_settings()
    send_system_email(user.email, "Reset your JobApply AI password", f"Reset your password: {s.public_base_url}/reset-password?token={token}")
    if s.environment in ("development", "test"):
        out["dev_reset_token"] = token
    return out


@router.post("/reset-password")
def reset_password(body: ResetPasswordIn, request: Request, db: Session = Depends(get_db)):
    problem = validate_password_strength(body.new_password)
    if problem:
        raise HTTPException(422, problem)
    token = body.token.strip()
    user = db.scalar(select(User).where(User.password_reset_token_hash == _sha(token)))
    if not user or user.deleted_at or not user.is_active or not user.password_reset_expires_at:
        raise HTTPException(400, "Invalid or expired reset link.")
    expires_at = user.password_reset_expires_at if user.password_reset_expires_at.tzinfo else user.password_reset_expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        db.commit()
        raise HTTPException(400, "Invalid or expired reset link.")
    user.password_hash = hash_password(body.new_password)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked_at=utcnow()))
    audit(db, user.id, "auth.password_reset", request=request)
    db.commit()
    return {"reset": True}


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limit("auth", get_settings().auth_rate_limit_per_minute))])
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    email = body.email.lower()
    locked, retry = limiter.exceeded(f"loginfail:{email}", 10, 900)  # per-account lockout on top of the per-IP rate limit
    if locked:
        raise HTTPException(429, "Too many failed attempts. Try again later.", headers={"Retry-After": str(retry)})
    user = db.scalar(select(User).where(User.email == email))
    pw_ok = verify_password(body.password, user.password_hash if user and user.password_hash else _DUMMY_HASH)
    if not user or not user.password_hash or not pw_ok or user.deleted_at or not user.is_active:
        limiter.hit(f"loginfail:{email}", 10, 900)
        audit(db, user.id if user else None, "auth.login_failed", request=request)
        db.commit()
        raise HTTPException(401, "Incorrect email or password.")
    limiter.clear(f"loginfail:{email}")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    audit(db, user.id, "auth.login", request=request)
    return issue_tokens(db, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _sha(body.refresh_token)))
    if not row:
        raise HTTPException(401, "Invalid refresh token")
    if row.revoked_at is not None:  # reuse of a rotated token → assume theft, kill the family
        db.execute(update(RefreshToken).where(RefreshToken.family_id == row.family_id).values(revoked_at=utcnow()))
        db.commit()
        raise HTTPException(401, "Refresh token reuse detected. Please sign in again.")
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    user = db.get(User, row.user_id)
    if exp < datetime.now(timezone.utc) or not user or user.deleted_at or not user.is_active:
        raise HTTPException(401, "Refresh token expired")
    row.revoked_at = utcnow()
    return issue_tokens(db, user, family=row.family_id)


@router.post("/logout", status_code=204)
def logout(body: RefreshIn, db: Session = Depends(get_db)):
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _sha(body.refresh_token)))
    if row:
        db.execute(update(RefreshToken).where(RefreshToken.family_id == row.family_id).values(revoked_at=utcnow()))
        db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def patch_me(body: UserPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.locale is not None:
        user.locale = body.locale
    db.commit()
    return user


@router.post("/change-password", status_code=204)
def change_password(body: PasswordChangeIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    problem = validate_password_strength(body.new_password)
    if problem:
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.new_password)
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked_at=utcnow()))  # sign out everywhere
    audit(db, user.id, "auth.password_changed", request=request)
    db.commit()


# ---- Google sign-in (authorization-code flow, server side)
@router.get("/google/login")
def google_login():
    s = get_settings()
    if not s.google_client_id:
        raise HTTPException(501, "Google sign-in is not configured.")
    state = sign_payload({"n": secrets.token_hex(8)}, 600, "google_login")
    q = {"client_id": s.google_client_id, "redirect_uri": f"{s.api_base_url}/api/v1/auth/google/callback", "response_type": "code",
         "scope": "openid email profile", "state": state, "prompt": "select_account"}
    return {"authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(q)}


@router.get("/google/callback")
def google_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    if not verify_payload(state, "google_login"):
        raise HTTPException(400, "Invalid sign-in state.")
    try:
        t = httpx.post("https://oauth2.googleapis.com/token", timeout=20, data={
            "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
            "redirect_uri": f"{s.api_base_url}/api/v1/auth/google/callback", "grant_type": "authorization_code"})
        t.raise_for_status()
        info = httpx.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {t.json()['access_token']}"}, timeout=20)
        info.raise_for_status()
        g = info.json()
    except (httpx.HTTPError, KeyError):
        raise HTTPException(400, "Google sign-in failed.")
    if not g.get("email") or not g.get("email_verified"):
        raise HTTPException(400, "Your Google email is not verified.")
    email = g["email"].lower()
    user = db.scalar(select(User).where((User.google_sub == g["sub"]) | (User.email == email)))
    if user and user.deleted_at:
        raise HTTPException(403, "This account was deleted.")
    if not user:
        user = User(email=email, google_sub=g["sub"], full_name=g.get("name", ""), email_verified=True, consent_terms_at=utcnow(), consent_ai_disclosure_at=utcnow())
        db.add(user)
        db.flush()
        db.add(Subscription(user_id=user.id, plan="free"))
        db.add(Profile(user_id=user.id, full_name=user.full_name, email=email))
    else:
        user.google_sub, user.email_verified = user.google_sub or g["sub"], True
    audit(db, user.id, "auth.google_login", request=request)
    tokens = issue_tokens(db, user)
    frag = urlencode({"access_token": tokens.access_token, "refresh_token": tokens.refresh_token})
    return RedirectResponse(f"{s.public_base_url}/auth/callback#{frag}")
