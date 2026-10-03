from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from celery.result import AsyncResult
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.routers.tasks import router
from src.tasks.celery_app import celery_app


class TaskStatusApiTests(TestCase):
    def test_pending_progress_success_and_failure(self) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        progress = {"current": 2, "total": 10, "progress": 20}
        result = {"success": True, "aggregated": 10, "errors": []}
        for state, value in (
            ("PENDING", None),
            ("PROGRESS", progress),
            ("SUCCESS", result),
            ("FAILURE", RuntimeError("private DB details")),
        ):
            with self.subTest(state=state):
                task = SimpleNamespace(
                    id="task-1",
                    backend=SimpleNamespace(
                        get_task_meta=Mock(
                            return_value={"status": state, "result": value}
                        )
                    ),
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

    def test_completion_between_backend_reads_keeps_one_consistent_snapshot(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        progress = {"current": 1, "total": 2, "progress": 50}
        for state, value in (
            ("SUCCESS", {"success": True, "aggregated": 2, "errors": []}),
            ("FAILURE", RuntimeError("private DB details")),
        ):
            with self.subTest(state=state):
                task = AsyncResult("race-task", app=celery_app)
                with (
                    patch.object(
                        task.backend,
                        "get_task_meta",
                        side_effect=[
                            {"status": "PROGRESS", "result": progress},
                            {"status": state, "result": value},
                        ],
                    ) as read,
                    patch(
                        "src.tasks.task_status.celery_app.AsyncResult",
                        return_value=task,
                    ),
                    TestClient(app, raise_server_exceptions=False) as client,
                ):
                    response = client.get("/api/v1/tasks/race-task")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["status"], "PROGRESS")
                self.assertEqual(response.json()["progress"], progress)
                self.assertIsNone(response.json()["result"])
                read.assert_called_once_with("race-task")
