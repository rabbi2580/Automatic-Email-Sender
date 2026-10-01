from __future__ import annotations

from app.models import User
from app.services.matching.engine import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS

DEFAULT_SETTINGS = {
    "weights": dict(DEFAULT_WEIGHTS),
    "thresholds": dict(DEFAULT_THRESHOLDS),
    "tone": "professional",
    "language": "en",
    "cv_template": "classic",
    "cv_font": "serif",
    "cv_pages": 1,
    "cv_style": "conservative",
    "include_cover_letter": True,
    "attach_docx": False,
    "auto_generate_for": ["strong", "potential"],
    "reminder_days_before_deadline": 3,
}


def get_user_settings(user: User) -> dict:
    merged = {**DEFAULT_SETTINGS, **(user.settings or {})}
    merged["weights"] = {**DEFAULT_WEIGHTS, **(merged.get("weights") or {})}
    merged["thresholds"] = {**DEFAULT_THRESHOLDS, **(merged.get("thresholds") or {})}
    return merged
