from celery import Celery

from src.core.config import settings

celery_app = Celery(
    "production_control",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "src.tasks.smoke",
        "src.tasks.product_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    control_queue_exclusive=True,
    event_queue_exclusive=True,
    task_track_started=True,
    result_expires=3600,
)
