"""Password hashing and JWT handling."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_ph = PasswordHasher()  # Argon2id defaults


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


def validate_password_strength(password: str) -> str | None:
    if len(password) < 10:
        return "Password must be at least 10 characters"
    if password.lower() == password or password.upper() == password:
        return "Password must mix upper and lower case letters"
    if not any(c.isdigit() for c in password):
        return "Password must contain a digit"
    return None


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    try:
        data = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return data if data.get("type") == "access" else None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def create_admin_access_token(admin_id: uuid.UUID) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(admin_id), "type": "admin_access", "iss": "jobapply-admin",
                       "iat": now, "exp": now + timedelta(minutes=s.admin_session_minutes),
                       "jti": secrets.token_hex(16)}, s.admin_secret_key, algorithm="HS256")


def decode_admin_access_token(token: str) -> dict | None:
    try:
        data = jwt.decode(token, get_settings().admin_secret_key, algorithms=["HS256"], issuer="jobapply-admin")
    except jwt.PyJWTError:
        return None
    return data if data.get("type") == "admin_access" else None
