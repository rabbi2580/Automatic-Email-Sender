from __future__ import annotations

import uuid
from typing import TypeVar

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models import User

bearer = HTTPBearer(auto_error=False)
M = TypeVar("M")


def get_current_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    data = decode_access_token(creds.credentials)
    if not data:
        raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    try:
        uid = uuid.UUID(data["sub"])
    except (ValueError, KeyError):
        raise HTTPException(401, "Invalid token")
    user = db.get(User, uid)
    if not user or user.deleted_at is not None or not user.is_active:
        raise HTTPException(401, "Account not available")
    request.state.user_id = str(user.id)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


def get_owned(db: Session, model: type[M], obj_id: uuid.UUID | str, user: User, *, allow_deleted: bool = False) -> M:
    """The ONLY sanctioned way to fetch a single tenant-owned row by id. Foreign rows look identical to missing rows (404)."""
    try:
        oid = obj_id if isinstance(obj_id, uuid.UUID) else uuid.UUID(str(obj_id))
    except ValueError:
        raise HTTPException(404, "Not found")
    obj = db.get(model, oid)
    if obj is None or getattr(obj, "user_id", None) != user.id:
        raise HTTPException(404, "Not found")
    if not allow_deleted and getattr(obj, "deleted_at", None) is not None:
        raise HTTPException(404, "Not found")
    return obj
