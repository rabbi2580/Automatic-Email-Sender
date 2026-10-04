from celery import Celery

from app.core.config import get_settings
from app.workers.tasks import TASKS

s = get_settings()
celery_app = Celery("jobapply", broker=s.redis_url, backend=s.redis_url)
celery_app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1, task_time_limit=600, task_soft_time_limit=540,
                       task_default_retry_delay=30, broker_connection_retry_on_startup=True, timezone="UTC",
                       beat_schedule={"poll-opted-in-mailboxes": {"task": "jobapply.poll_mailboxes", "schedule": 300.0},
                                     "create-reminders": {"task": "jobapply.create_reminders", "schedule": 300.0}})

for _name, _fn in TASKS.items():
    celery_app.task(name=f"jobapply.{_name}", bind=False, max_retries=2, autoretry_for=(ConnectionError,))(_fn)
