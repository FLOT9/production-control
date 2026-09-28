from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.v1.schemas.batch import BatchImportTaskStatusRead
from src.application.exceptions import BatchCsvFileError
from src.application.importers.batch_csv import REQUIRED_HEADERS, BatchCsvParser
from src.tasks.batch_tasks import _import_batches_csv
from src.tasks.task_status import get_task_status


def csv_row(*, extra_value: bool = False) -> bytes:
    values = {
        "task_description": "Task",
        "work_center_id": "1",
        "shift": "Day",
        "team": "A",
        "batch_number": "1",
        "batch_date": "2026-09-25",
        "nomenclature": "Item",
        "ekn_code": "EKN",
        "shift_start": "2026-09-25T08:00:00+05:00",
        "shift_end": "2026-09-25T09:00:00+05:00",
    }
    headers = sorted(REQUIRED_HEADERS)
    row = ";".join(values[name] for name in headers)
    if extra_value:
        row += ";unexpected"
    return (";".join(headers) + "\n" + row + "\n").encode()


class BatchCsvParserTests(TestCase):
    def test_valid_row_is_accepted(self):
        result = BatchCsvParser().parse(csv_row())

        self.assertEqual(len(result.valid_rows), 1)
        self.assertEqual(result.errors, [])

    def test_extra_value_is_reported_as_row_error(self):
        result = BatchCsvParser().parse(csv_row(extra_value=True))

        self.assertEqual(result.valid_rows, [])
        self.assertEqual(result.errors[0].row_number, 2)
        self.assertEqual(
            result.errors[0].reason,
            "CSV row has more values than headers",
        )


class BatchImportTaskTests(IsolatedAsyncioTestCase):
    async def test_invalid_utf8_becomes_public_file_error(self):
        storage = SimpleNamespace(download=MagicMock(return_value=b"\xff"))
        client = SimpleNamespace(aclose=AsyncMock())
        session_context = MagicMock()
        session_context.__aenter__ = AsyncMock(return_value=object())
        session_context.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.tasks.batch_tasks.create_object_storage", return_value=storage),
            patch("src.tasks.batch_tasks.create_redis_client", return_value=client),
            patch(
                "src.tasks.batch_tasks.async_session_maker",
                return_value=session_context,
            ),
            patch("src.tasks.batch_tasks.UnitOfWork"),
            patch("src.tasks.batch_tasks.build_batch_service"),
            patch("src.tasks.batch_tasks.dispose_engine", new_callable=AsyncMock),
            self.assertRaisesRegex(BatchCsvFileError, "UTF-8"),
        ):
            await _import_batches_csv("import.csv")

        storage.download.assert_called_once_with("imports", "import.csv")
        client.aclose.assert_awaited_once()


class BatchImportStatusTests(TestCase):
    @patch("src.tasks.task_status.celery_app.AsyncResult")
    def test_file_error_is_visible_in_failed_status(self, async_result):
        async_result.return_value = SimpleNamespace(
            id="task-1",
            status="FAILURE",
            result=BatchCsvFileError("CSV must be UTF-8 encoded"),
        )

        response = BatchImportTaskStatusRead(**get_task_status("task-1"))

        self.assertEqual(response.status, "FAILURE")
        self.assertIsNone(response.result)
        self.assertEqual(response.error, "CSV must be UTF-8 encoded")

    @patch("src.tasks.task_status.celery_app.AsyncResult")
    def test_internal_error_is_not_exposed(self, async_result):
        async_result.return_value = SimpleNamespace(
            id="task-1",
            status="FAILURE",
            result=RuntimeError("secret database URL"),
        )

        response = BatchImportTaskStatusRead(**get_task_status("task-1"))

        self.assertEqual(response.error, "Task failed; check worker logs")
