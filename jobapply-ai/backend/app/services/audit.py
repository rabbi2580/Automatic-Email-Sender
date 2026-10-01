from __future__ import annotations

import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, user_id: uuid.UUID | None, action: str, *, entity_type: str | None = None, entity_id: str | uuid.UUID | None = None,
          request: Request | None = None, **meta) -> None:
    """Append an audit record. Never put CV/job content or secrets in `meta`."""
    ip = None
    if request is not None:
        from app.core.ratelimit import client_ip

        ip = client_ip(request)
    db.add(AuditLog(user_id=user_id, action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id else None, ip=ip, meta=meta))
