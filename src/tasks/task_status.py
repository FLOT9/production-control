from src.application.exceptions import BatchCsvFileError
from src.tasks.celery_app import celery_app


def get_task_status(task_id: str) -> dict[str, object]:
    task = celery_app.AsyncResult(task_id)
    task_status = task.status

    error = None
    if task_status == "FAILURE":
        error = (
            str(task.result)
            if isinstance(task.result, BatchCsvFileError)
            else "Task failed; check worker logs"
        )

    return {
        "task_id": task.id,
        "status": task_status,
        "progress": task.info if task_status == "PROGRESS" else None,
        "result": task.result if task_status == "SUCCESS" else None,
        "error": error,
    }
