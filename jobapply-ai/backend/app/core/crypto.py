"""Encryption of secrets at rest (OAuth tokens, SMTP passwords) and signed tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    s = get_settings()
    key = s.encryption_key
    if not key:
        # Development/test only: derive a stable key from SECRET_KEY.
        key = base64.urlsafe_b64encode(hashlib.sha256(s.secret_key.encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt_str(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_str(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - corrupted/rotated key
        raise ValueError("Unable to decrypt stored secret") from exc


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_payload(payload: dict, ttl_seconds: int, purpose: str) -> str:
    """Create a compact HMAC-signed token (used for confirmation tokens, signed URLs, OAuth state)."""
    body = dict(payload, exp=int(time.time()) + ttl_seconds, pur=purpose)
    raw = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(get_settings().secret_key.encode(), f"{purpose}.{raw}".encode(), hashlib.sha256).digest()
    return f"{raw}.{_b64(sig)}"


def verify_payload(token: str, purpose: str) -> dict | None:
    try:
        raw, sig = token.split(".", 1)
        expected = hmac.new(get_settings().secret_key.encode(), f"{purpose}.{raw}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64(sig), expected):
            return None
        body = json.loads(_unb64(raw))
    except Exception:
        return None
    if body.get("pur") != purpose or body.get("exp", 0) < time.time():
        return None
    return body
