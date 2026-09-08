from src.tasks.celery_app import celery_app


def get_task_status(task_id: str) -> dict[str, object]:
    task = celery_app.AsyncResult(task_id)
    task_status = task.status

    return {
        "task_id": task.id,
        "status": task_status,
        "result": task.result if task_status == "SUCCESS" else None,
    }
