from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.helpers import resume_out
from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import Job, Profile, Resume, User
from app.schemas.ai import ProfileExtraction
from app.services import pipeline
from app.services.audit import audit
from app.services.profile_view import profile_snapshot
from app.schemas.api import ProfilePatch

router = APIRouter(prefix="/profile", tags=["profile"])


def _profile(db: Session, user: User) -> Profile:
    p = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if not p:
        p = Profile(user_id=user.id, full_name=user.full_name, email=user.email)
        db.add(p)
        db.commit()
    return p


def _completeness(p: Profile) -> dict:
    checks = {"contact": bool(p.full_name and p.email), "skills": bool(p.skills), "education": bool(p.educations), "experience_or_projects": bool(p.experiences or p.projects),
              "target_roles": bool(p.target_roles), "location": bool(p.location)}
    return {"percent": round(100 * sum(checks.values()) / len(checks)), "missing": [k for k, v in checks.items() if not v]}


def profile_out(db: Session, p: Profile) -> dict:
    snap = profile_snapshot(p)
    snap.update({"salary_expectation": p.salary_expectation, "work_authorization": p.work_authorization, "other_preferences": p.other_preferences,
                 "completeness": _completeness(p), "source_resume_id": str(p.source_resume_id) if p.source_resume_id else None})
    master = db.scalar(select(Resume).where(Resume.user_id == p.user_id, Resume.deleted_at.is_(None)).order_by(Resume.created_at.desc()))
    snap["resume"] = resume_out(master) if master else None
    return snap


@router.get("")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_out(db, _profile(db, user))


@router.patch("")
def patch_profile(body: ProfilePatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _profile(db, user)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k == "years_experience":
            setattr(p, k, v)
    db.commit()
    return profile_out(db, p)


@router.put("/structured")
def replace_structured(body: ProfileExtraction, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Full replacement of the structured profile (used by the profile editor). Does not touch the original CV file."""
    p = _profile(db, user)
    pipeline.apply_extraction(db, user, body, None, overwrite_scalars=True)
    audit(db, user.id, "profile.replace", entity_type="profile", entity_id=p.id)
    db.commit()
    for job in db.scalars(select(Job).where(Job.user_id == user.id, Job.deleted_at.is_(None), Job.status.in_(("completed", "requires_review")))).all():
        pipeline.match_job(db, user, job)
    db.commit()
    return profile_out(db, _profile(db, user))
