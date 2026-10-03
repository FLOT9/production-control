from src.tasks.celery_app import celery_app


@celery_app.task(name="smoke.ping")
def ping() -> str:
    return "pong"
