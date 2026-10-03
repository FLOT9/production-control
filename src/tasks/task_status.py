from src.application.exceptions import (
    BatchCsvFileError,
    BatchExportFileError,
    ProductionSummaryEmptyError,
)
from src.tasks.celery_app import celery_app


def get_task_status(task_id: str) -> dict[str, object]:
    task = celery_app.AsyncResult(task_id)
    # Separate AsyncResult properties can observe different worker states.
    metadata = task.backend.get_task_meta(task.id)
    task_status = metadata["status"]
    task_result = metadata["result"]

    error = None
    if task_status == "FAILURE":
        error = (
            str(task_result)
            if isinstance(
                task_result,
                BatchCsvFileError | BatchExportFileError | ProductionSummaryEmptyError,
            )
            else "Task failed; check worker logs"
        )

    return {
        "task_id": task.id,
        "status": task_status,
        "progress": task_result if task_status == "PROGRESS" else None,
        "result": task_result if task_status == "SUCCESS" else None,
        "error": error,
    }
