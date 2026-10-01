"""Background task bodies. They open their own DB session so they behave identically inline and under Celery."""
from __future__ import annotations

import logging
import uuid

from app.core.db import SessionLocal
from app.models import Application, Job, Resume, User
from app.services import pipeline

log = logging.getLogger("jobapply.tasks")


def task_process_resume(resume_id: str) -> None:
    with SessionLocal() as db:
        try:
            pipeline.process_resume(db, uuid.UUID(resume_id))
        except Exception as exc:  # noqa: BLE001 - never leave a row in "processing"
            log.exception("process_resume failed")
            db.rollback()
            r = db.get(Resume, uuid.UUID(resume_id))
            if r:
                r.status, r.status_reason = "failed", f"Unexpected error ({type(exc).__name__}). Please try again."
                db.commit()


def task_process_job(job_id: str) -> None:
    with SessionLocal() as db:
        try:
            pipeline.process_job(db, uuid.UUID(job_id))
        except Exception as exc:  # noqa: BLE001
            log.exception("process_job failed")
            db.rollback()
            j = db.get(Job, uuid.UUID(job_id))
            if j:
                j.status, j.status_reason = "failed", f"Unexpected error ({type(exc).__name__}). You can retry or enter the details manually."
                db.commit()


def task_generate_application(user_id: str, job_id: str, tone: str | None, language: str | None, options: dict | None) -> None:
    with SessionLocal() as db:
        user = db.get(User, uuid.UUID(user_id))
        try:
            pipeline.generate_application(db, user, uuid.UUID(job_id), tone=tone, language=language, options=options)
        except Exception as exc:  # noqa: BLE001
            log.exception("generate_application failed")
            db.rollback()
            app = db.query(Application).filter_by(user_id=user.id, job_id=uuid.UUID(job_id)).first()
            if app:
                app.generation_status, app.generation_reason = "failed", f"{exc}"[:400] if isinstance(exc, ValueError) else f"Unexpected error ({type(exc).__name__})."
                db.commit()


TASKS = {"process_resume": task_process_resume, "process_job": task_process_job, "generate_application": task_generate_application}
