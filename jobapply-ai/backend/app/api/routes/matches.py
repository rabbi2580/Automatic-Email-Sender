from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.helpers import job_out
from app.core.db import get_db
from app.core.deps import get_current_user, get_owned
from app.models import Job, JobMatch, User
from app.services import pipeline

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("")
def list_matches(classification: str | None = None, min_score: float = Query(default=0, ge=0, le=100), hide_duplicates: bool = True,
                 limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Job, JobMatch).join(JobMatch, JobMatch.job_id == Job.id).where(Job.user_id == user.id, Job.deleted_at.is_(None), JobMatch.score >= min_score)
    if classification:
        stmt = stmt.where(JobMatch.classification == classification)
    if hide_duplicates:
        stmt = stmt.where(Job.duplicate_of_id.is_(None))
    rows = db.execute(stmt.order_by(JobMatch.score.desc()).limit(limit).offset(offset)).all()
    return [job_out(j, m) for j, m in rows]


@router.post("/recompute")
def recompute(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Re-score every job with the current profile and Settings (weights/thresholds)."""
    n = 0
    for j in db.scalars(select(Job).where(Job.user_id == user.id, Job.deleted_at.is_(None), Job.status.in_(("completed", "requires_review")))):
        if pipeline.match_job(db, user, j):
            n += 1
    db.commit()
    return {"recomputed": n}


@router.get("/{job_id}")
def get_match(job_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    j = get_owned(db, Job, job_id, user)
    m = db.scalar(select(JobMatch).where(JobMatch.job_id == j.id))
    if not m:
        raise HTTPException(404, "No match yet. Complete your profile and analyse the job.")
    return job_out(j, m)
