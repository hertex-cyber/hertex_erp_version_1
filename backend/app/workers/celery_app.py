from celery import Celery

from app.core.config import settings
from app.tasks.settings_sweeps import BEAT_SCHEDULE
from app.tasks.settings_sweeps import register as register_settings_sweeps

celery_app = Celery(
    "hertex",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

register_settings_sweeps(celery_app)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=60 * 60 * 24,
    broker_connection_retry_on_startup=True,
    beat_scheduler="celery.beat:PersistentScheduler",
    task_default_retry_delay=5,
    worker_send_task_events=True,
    beat_schedule={
        "refresh-analytics-cache": {
            "task": "hertex.refresh_analytics",
            "schedule": 60 * 15,
        },
        "scan-overdue-invoices": {
            "task": "hertex.scan_overdue_invoices",
            "schedule": 60 * 60 * 6,
        },
        **BEAT_SCHEDULE,
    },
)
