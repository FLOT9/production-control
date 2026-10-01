from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from src.core.config import settings
from src.core.logging import configure_logging


@setup_logging.connect
def configure_celery_logging(**_kwargs: object) -> None:
    configure_logging()


celery_app = Celery(
    "production_control",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "src.tasks.smoke",
        "src.tasks.product_tasks",
        "src.tasks.report_tasks",
        "src.tasks.batch_tasks",
        "src.tasks.webhook_tasks",
        "src.tasks.analytics_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.production_timezone,
    enable_utc=True,
    control_queue_exclusive=True,
    event_queue_exclusive=True,
    task_track_started=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
    result_expires=3600,
    beat_schedule={
        "update-cached-statistics": {
            "task": "analytics.update_cached_statistics",
            "schedule": crontab(minute="*/5"),
        },
        "auto-close-expired-batches": {
            "task": "batches.auto_close_expired",
            "schedule": crontab(hour=1, minute=0),
        },
        "dispatch-ready-webhooks": {
            "task": "webhooks.dispatch",
            "schedule": 10.0,
            "kwargs": {"limit": 100},
        },
    },
)
