from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import get_current_user, get_owned
from app.models import Application, CalendarEvent, InterviewPrep, Job, User
from app.models.base import utcnow
from app.schemas.api import CalendarEventIn

router = APIRouter(tags=["planning"])


@router.get("/applications/{app_id}/interview-prep")
def get_prep(app_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = get_owned(db, Application, app_id, user)
    prep = db.scalar(select(InterviewPrep).where(InterviewPrep.user_id == user.id, InterviewPrep.application_id == app.id))
    job = db.get(Job, app.job_id)
    if not prep:
        skills = list(job.required_skills or []) if job else []
        questions = [{"question": f"How would you demonstrate experience with {skill}?", "type": "skill", "answer": ""} for skill in skills[:8]]
        questions += [{"question": "Tell us about a relevant project and the result you achieved.", "type": "behavioral", "answer": ""},
                      {"question": "Why are you interested in this role?", "type": "motivation", "answer": ""}]
        prep = InterviewPrep(user_id=user.id, application_id=app.id, questions=questions); db.add(prep); db.commit(); db.refresh(prep)
    return {"application_id": str(app.id), "questions": prep.questions, "notes": prep.notes, "completed_at": prep.completed_at.isoformat() if prep.completed_at else None}


@router.put("/applications/{app_id}/interview-prep")
def update_prep(app_id: uuid.UUID, body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = get_owned(db, Application, app_id, user)
    prep = db.scalar(select(InterviewPrep).where(InterviewPrep.user_id == user.id, InterviewPrep.application_id == app.id))
    if not prep: raise HTTPException(404, "Interview prep not found")
    if "questions" in body and not isinstance(body["questions"], list): raise HTTPException(422, "questions must be a list")
    prep.questions = body.get("questions", prep.questions); prep.notes = str(body.get("notes", prep.notes))[:10000]
    if body.get("complete"): prep.completed_at = utcnow()
    db.commit(); return {"questions": prep.questions, "notes": prep.notes, "completed_at": prep.completed_at.isoformat() if prep.completed_at else None}


@router.get("/calendar/events")
def list_calendar(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"id": str(e.id), "application_id": str(e.application_id) if e.application_id else None, "title": e.title, "starts_at": e.starts_at.isoformat(), "ends_at": e.ends_at.isoformat() if e.ends_at else None, "location": e.location, "provider": e.provider, "status": e.status}
            for e in db.scalars(select(CalendarEvent).where(CalendarEvent.user_id == user.id).order_by(CalendarEvent.starts_at).limit(200)).all()]


@router.post("/calendar/events", status_code=201)
def create_calendar(body: CalendarEventIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.application_id: get_owned(db, Application, body.application_id, user)
    if body.ends_at and body.ends_at <= body.starts_at: raise HTTPException(422, "Event end must be after its start")
    e = CalendarEvent(user_id=user.id, application_id=body.application_id, title=body.title.strip(), starts_at=body.starts_at, ends_at=body.ends_at, location=body.location.strip())
    db.add(e); db.commit(); db.refresh(e)
    return {"id": str(e.id), "title": e.title, "starts_at": e.starts_at.isoformat()}


@router.delete("/calendar/events/{event_id}", status_code=204)
def delete_calendar(event_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = get_owned(db, CalendarEvent, event_id, user); db.delete(e); db.commit()
