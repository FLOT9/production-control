from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.routers.tasks import router


class TaskStatusApiTests(TestCase):
    def test_pending_progress_success_and_failure(self) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        progress = {"current": 2, "total": 10, "progress": 20}
        result = {"success": True, "aggregated": 10, "errors": []}
        for state, info, value in (
            ("PENDING", None, None),
            ("PROGRESS", progress, progress),
            ("SUCCESS", result, result),
            (
                "FAILURE",
                RuntimeError("private DB details"),
                RuntimeError("private DB details"),
            ),
        ):
            with self.subTest(state=state):
                task = SimpleNamespace(
                    id="task-1", status=state, info=info, result=value
                )
                with (
                    patch(
                        "src.tasks.task_status.celery_app.AsyncResult",
                        return_value=task,
                    ),
                    TestClient(app) as client,
                ):
                    response = client.get("/api/v1/tasks/task-1")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["status"], state)
                self.assertEqual(
                    data["progress"], progress if state == "PROGRESS" else None
                )
                self.assertEqual(data["result"], result if state == "SUCCESS" else None)
                if state == "FAILURE":
                    self.assertEqual(data["error"], "Task failed; check worker logs")
                    self.assertNotIn("private DB details", response.text)
