from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.routers import api_v1_router
from src.application.exceptions import BatchCsvFileError, BatchExportFileError

STATUS_PATHS = (
    "/api/v1/tasks/task-1",
    "/api/v1/products/tasks/task-1",
    "/api/v1/reports/tasks/task-1",
    "/api/v1/batches/import/tasks/task-1",
    "/api/v1/batches/export/tasks/task-1",
)


class LegacyTaskStatusApiTests(TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(api_v1_router)
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def assert_status_on_all_routes(self, state, value, *, error=None):
        metadata = Mock(return_value={"status": state, "result": value})
        task = SimpleNamespace(
            id="task-1", backend=SimpleNamespace(get_task_meta=metadata)
        )
        expected = {
            "task_id": "task-1",
            "status": state,
            "progress": value if state == "PROGRESS" else None,
            "result": value if state == "SUCCESS" else None,
            "error": error,
        }
        with patch("src.tasks.task_status.celery_app.AsyncResult", return_value=task):
            for path in STATUS_PATHS:
                with self.subTest(
                    path=path, state=state, value_type=type(value).__name__
                ):
                    metadata.reset_mock()
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json(), expected)
                    metadata.assert_called_once_with("task-1")

    def test_all_success_result_types_work_on_every_legacy_route(self):
        results = [
            {
                "report_id": "report-1",
                "bucket": "reports",
                "object_name": "summary.xlsx",
            },
            {
                "processed": [{"row_number": 2, "batch_id": 1}],
                "failed": [{"row_number": 3, "reason": "Bad row"}],
            },
            {
                "success": False,
                "total": 2,
                "aggregated": 1,
                "failed": 1,
                "errors": [{"unique_code": "A", "reason": "Wrong batch"}],
            },
            {"delivery_id": 1, "delivered": True},
            {"checked": 10, "closed": 2, "skipped": 8},
            {"updated_batches": 10},
            {"email_status": "sent", "report_id": "report-1"},
        ]
        for result in results:
            self.assert_status_on_all_routes("SUCCESS", result)

    def test_states_progress_and_safe_errors_match_general_endpoint(self):
        for state in ("PENDING", "STARTED", "REVOKED"):
            self.assert_status_on_all_routes(state, None)
        self.assert_status_on_all_routes("RETRY", RuntimeError("private details"))
        self.assert_status_on_all_routes(
            "PROGRESS", {"current": 1, "total": 2, "progress": 50}
        )
        self.assert_status_on_all_routes(
            "FAILURE",
            RuntimeError("private DB details"),
            error="Task failed; check worker logs",
        )
        self.assert_status_on_all_routes(
            "FAILURE",
            BatchCsvFileError("Invalid CSV header"),
            error="Invalid CSV header",
        )
        self.assert_status_on_all_routes(
            "FAILURE",
            BatchExportFileError("Text exceeds Excel limit"),
            error="Text exceeds Excel limit",
        )
