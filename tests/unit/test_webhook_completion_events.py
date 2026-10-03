import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from src.api.dependencies.webhooks import get_webhook_subscription_service
from src.api.v1.routers.webhooks import legacy_router, router
from src.application.dto.stored_report import StoredReport
from src.application.exceptions import BatchCsvFileError
from src.tasks import batch_tasks, report_tasks
from tests.unit.test_batch_csv_import import csv_row
from tests.unit.test_batch_transfer import excel_bytes


def make_uow():
    return SimpleNamespace(
        webhook_subscriptions=SimpleNamespace(
            find_active_by_event=AsyncMock(
                return_value=[SimpleNamespace(id=9, url="https://example.com/hook")]
            )
        ),
        webhook_deliveries=SimpleNamespace(
            create=AsyncMock(return_value=SimpleNamespace(id=15))
        ),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )


@contextmanager
def task_resources(module, uow):
    session = AsyncMock()
    with (
        patch.object(module, "async_session_maker", return_value=session),
        patch.object(module, "UnitOfWork", return_value=uow),
        patch.object(module, "dispose_engine", new_callable=AsyncMock) as dispose,
    ):
        yield
    dispose.assert_awaited_once()


@pytest.mark.parametrize("prefix", ["webhooks", "webhook-subscriptions"])
def test_subscription_routes_accept_completion_events_on_create_and_update(prefix):
    events = ["report_generated", "import_completed"]
    now = datetime.now(UTC)
    item = SimpleNamespace(
        id=9,
        url="https://example.com/hook",
        events=events,
        is_active=True,
        retry_count=3,
        timeout_seconds=10,
        created_at=now,
        updated_at=now,
    )
    service = SimpleNamespace(
        create=AsyncMock(return_value=item), update=AsyncMock(return_value=item)
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(legacy_router, prefix="/api/v1")
    app.dependency_overrides[get_webhook_subscription_service] = lambda: service
    with TestClient(app) as client:
        created = client.post(
            f"/api/v1/{prefix}",
            json={"url": item.url, "events": events, "secret_key": "x" * 32},
        )
        assert created.status_code == 201
        assert created.json()["events"] == events
        updated = client.patch(f"/api/v1/{prefix}/9", json={"events": events})
        assert updated.status_code == 200
        assert updated.json()["events"] == events
    assert service.create.await_args.kwargs["events"] == events
    service.update.assert_awaited_once_with(9, {"events": events})


@pytest.mark.parametrize(
    "kind,format",
    [("batch", "excel"), ("batch", "pdf"), ("production_summary", "excel")],
)
def test_report_delivery_is_created_after_upload_and_committed_before_result(
    kind, format
):
    async def scenario():
        uow = make_uow()
        report = StoredReport(uuid4(), "reports", "uploaded-report")
        generator_path = (
            "BatchReportFileService" if kind == "batch" else "ProductionSummaryService"
        )
        uploaded = False

        async def upload(*args):
            nonlocal uploaded
            uow.webhook_subscriptions.find_active_by_event.assert_not_awaited()
            uploaded = True
            return report

        async def create(**kwargs):
            assert uploaded
            uow.commit.assert_not_awaited()
            return SimpleNamespace(id=15)

        uow.webhook_deliveries.create.side_effect = create
        with (
            task_resources(report_tasks, uow),
            patch.object(report_tasks, generator_path) as generator,
        ):
            generator.return_value.generate_and_upload = AsyncMock(side_effect=upload)
            if kind == "batch":
                result = await report_tasks._generate_batch_report(
                    42, format, "report-task"
                )
                assert result == report
            else:
                result = await report_tasks._generate_production_summary("report-task")
                assert result["report_id"] == str(report.report_id)

        uow.commit.assert_awaited_once()
        uow.webhook_subscriptions.find_active_by_event.assert_awaited_once_with(
            "report_generated"
        )
        saved = uow.webhook_deliveries.create.await_args.kwargs
        assert saved["subscription_id"] == 9
        assert saved["event_type"] == "report_generated"
        payload = saved["payload"]
        assert set(payload) == {"event_id", "event", "timestamp", "data"}
        assert json.loads(saved["request_body"]) == payload
        data = payload["data"]
        assert data["task_id"] == "report-task"
        assert data["report_id"] == str(report.report_id)
        assert data["report_type"] == kind
        assert data["format"] == format
        assert str(report.report_id) in data["download_url"]
        if kind == "batch":
            assert data["batch_id"] == 42
            assert data["download_url"].endswith(f"/download?format={format}")

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "kind,format",
    [("batch", "excel"), ("batch", "pdf"), ("production_summary", "excel")],
)
def test_report_generation_or_upload_failure_does_not_create_completion_event(
    kind, format
):
    async def scenario():
        uow = make_uow()
        generator_path = (
            "BatchReportFileService" if kind == "batch" else "ProductionSummaryService"
        )
        with (
            task_resources(report_tasks, uow),
            patch.object(report_tasks, generator_path) as generator,
        ):
            generator.return_value.generate_and_upload = AsyncMock(
                side_effect=RuntimeError("generation or upload failed")
            )
            with pytest.raises(RuntimeError):
                if kind == "batch":
                    await report_tasks._generate_batch_report(42, format, "report-task")
                else:
                    await report_tasks._generate_production_summary("report-task")
        uow.webhook_subscriptions.find_active_by_event.assert_not_awaited()
        uow.webhook_deliveries.create.assert_not_awaited()
        uow.commit.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("format", ["csv", "excel"])
@pytest.mark.parametrize("outcome", ["success", "partial", "all_rows_failed"])
def test_finished_import_creates_event_with_actual_row_outcomes(format, outcome):
    async def scenario():
        uow = make_uow()
        if format == "csv":
            data = csv_row(extra_value=outcome == "all_rows_failed")
            if outcome == "partial":
                data += csv_row(extra_value=True).splitlines()[1] + b"\n"
        else:
            rows = [{}] if outcome != "all_rows_failed" else []
            if outcome != "success":
                rows.append({"batch_number": 3000000000})
            data = excel_bytes(rows)
        storage = SimpleNamespace(download=Mock(return_value=data))
        client = SimpleNamespace(aclose=AsyncMock())
        batch_service = SimpleNamespace(
            uow=uow, create=AsyncMock(return_value=SimpleNamespace(id=42))
        )
        with (
            task_resources(batch_tasks, uow),
            patch.object(batch_tasks, "create_object_storage", return_value=storage),
            patch.object(batch_tasks, "create_redis_client", return_value=client),
            patch.object(
                batch_tasks, "build_batch_service", return_value=batch_service
            ),
        ):
            result = await batch_tasks._import_batches(
                "imports/file", format, "import-task"
            )
        uow.commit.assert_awaited_once()
        client.aclose.assert_awaited_once()
        uow.webhook_subscriptions.find_active_by_event.assert_awaited_once_with(
            "import_completed"
        )
        saved = uow.webhook_deliveries.create.await_args.kwargs
        assert json.loads(saved["request_body"]) == saved["payload"]
        assert saved["payload"]["event"] == "import_completed"
        data = saved["payload"]["data"]
        imported = 0 if outcome == "all_rows_failed" else 1
        failed = 0 if outcome == "success" else 1
        assert data["task_id"] == "import-task"
        assert data["format"] == format
        assert data["total"] == imported + failed
        assert data["imported"] == imported
        assert data["failed"] == failed
        assert data["batch_ids"] == ([42] if imported else [])
        assert data["errors"] == result["failed"]
        assert len(result["processed"]) == imported
        assert len(result["failed"]) == failed

    asyncio.run(scenario())


@pytest.mark.parametrize("format", ["csv", "excel"])
def test_invalid_import_file_does_not_create_completion_event(format):
    async def scenario():
        uow = make_uow()
        client = SimpleNamespace(aclose=AsyncMock())
        with (
            task_resources(batch_tasks, uow),
            patch.object(
                batch_tasks,
                "create_object_storage",
                return_value=SimpleNamespace(
                    download=Mock(return_value=b"invalid file")
                ),
            ),
            patch.object(batch_tasks, "create_redis_client", return_value=client),
            patch.object(batch_tasks, "build_batch_service"),
            pytest.raises(BatchCsvFileError),
        ):
            await batch_tasks._import_batches("imports/file", format, "import-task")
        client.aclose.assert_awaited_once()
        uow.webhook_subscriptions.find_active_by_event.assert_not_awaited()
        uow.webhook_deliveries.create.assert_not_awaited()
        uow.commit.assert_not_awaited()

    asyncio.run(scenario())


def test_database_failure_during_import_does_not_report_completion():
    async def scenario():
        uow = make_uow()
        client = SimpleNamespace(aclose=AsyncMock())
        service = SimpleNamespace(
            uow=uow,
            create=AsyncMock(
                side_effect=OperationalError("SQL", {}, Exception("offline"))
            ),
        )
        with (
            task_resources(batch_tasks, uow),
            patch.object(
                batch_tasks,
                "create_object_storage",
                return_value=SimpleNamespace(download=Mock(return_value=csv_row())),
            ),
            patch.object(batch_tasks, "create_redis_client", return_value=client),
            patch.object(batch_tasks, "build_batch_service", return_value=service),
            pytest.raises(OperationalError),
        ):
            await batch_tasks._import_batches("imports/file", "csv", "import-task")
        uow.webhook_deliveries.create.assert_not_awaited()
        uow.commit.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "task,helper,args,helper_args,result",
    [
        (
            report_tasks.generate_batch_report,
            "src.tasks.report_tasks._generate_batch_report",
            (42, "pdf"),
            (42, "pdf", "task-id"),
            StoredReport(uuid4(), "reports", "report.pdf"),
        ),
        (
            report_tasks.generate_production_summary,
            "src.tasks.report_tasks._generate_production_summary",
            (),
            ("task-id",),
            {},
        ),
        (
            batch_tasks.import_batches_csv,
            "src.tasks.batch_tasks._import_batches_csv",
            ("file.csv",),
            ("file.csv", "task-id"),
            {},
        ),
        (
            batch_tasks.import_batches_file,
            "src.tasks.batch_tasks._import_batches",
            ("file.xlsx", "excel"),
            ("file.xlsx", "excel", "task-id"),
            {},
        ),
    ],
)
def test_completion_events_receive_the_celery_task_id(
    task, helper, args, helper_args, result
):
    task.push_request(id="task-id")
    try:
        with patch(helper, new=AsyncMock(return_value=result)) as operation:
            task.run(*args)
        operation.assert_awaited_once_with(*helper_args)
    finally:
        task.pop_request()
