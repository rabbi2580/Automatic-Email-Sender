"""Enqueue background work. TASK_MODE=inline runs synchronously (dev/tests); TASK_MODE=celery uses the Redis queue."""
from __future__ import annotations

from app.core.config import get_settings
from app.workers.tasks import TASKS


def enqueue(name: str, *args) -> None:
    if get_settings().task_mode == "celery":
        from app.workers.celery_app import celery_app

        celery_app.send_task(f"jobapply.{name}", args=list(args))
    else:
        TASKS[name](*args)
