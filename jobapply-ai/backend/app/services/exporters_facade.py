"""Small helpers used by routes so they do not import exporters/ORM details directly."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Profile, User
from app.services.generation import exporters  # noqa: F401  (re-exported for routes)


def get_profile(db: Session, user: User) -> Profile:
    return db.scalar(select(Profile).where(Profile.user_id == user.id))


def render_letter(kind: str, letter: dict, header: dict, options: dict) -> bytes:
    if kind == "cover_letter_pdf":
        return exporters.render_cover_letter_pdf(letter, header, options)
    return exporters.render_cover_letter_docx(letter, header)
