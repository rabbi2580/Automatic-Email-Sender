"""Application status machine + event log."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Application, ApplicationEvent
from app.models.base import utcnow

ORDER = ["saved", "analyzing", "matched", "cv_generated", "awaiting_review", "approved", "sent", "application_confirmed", "interview", "offer"]
TERMINAL = {"rejected", "offer", "withdrawn"}
# who may move where. System-driven steps are not exposed to users except via dedicated endpoints.
USER_TRANSITIONS: dict[str, set[str]] = {
    "awaiting_review": {"approved", "withdrawn", "saved"},
    "approved": {"awaiting_review", "withdrawn"},
    "cv_generated": {"awaiting_review", "withdrawn"},
    "matched": {"withdrawn"},
    "saved": {"withdrawn"},
    "analyzing": {"withdrawn"},
    "sent": {"application_confirmed", "interview", "rejected", "offer", "withdrawn"},
    "application_confirmed": {"interview", "rejected", "offer", "withdrawn"},
    "interview": {"offer", "rejected", "withdrawn"},
    "rejected": {"interview"},
    "offer": {"withdrawn", "interview"},
    "withdrawn": {"saved"},
}


class TransitionError(Exception):
    pass


def transition(db: Session, app: Application, to: str, *, actor: str = "system", detail: dict | None = None, force: bool = False) -> None:
    if app.status == to:
        return
    if actor == "user" and not force and to not in USER_TRANSITIONS.get(app.status, set()):
        raise TransitionError(f"Cannot move an application from '{app.status}' to '{to}'.")
    old = app.status
    app.status = to
    app.updated_at = utcnow()
    db.add(ApplicationEvent(user_id=app.user_id, application_id=app.id, type="status_change", from_status=old, to_status=to,
                            detail={"actor": actor, **(detail or {})}))
