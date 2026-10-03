import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.api.dependencies.batches import get_batch_service
from src.api.v1.routers.batches import router
from src.application.dto import BatchFilters
from src.data.models import Batch, WorkCenter
from src.data.repositories.batch_repository import BatchRepository
from src.storage.batch_list_cache import BatchListCache
from src.tasks.batch_tasks import export_batches_csv


class BatchFilterRepositoryTests(IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        WorkCenter.__table__.create(engine)
        Batch.__table__.create(engine)
        session = Session(engine)
        self.addCleanup(session.close)
        session.add(WorkCenter(id=1, identifier="WC1", name="Line 1"))
        for number, closed, shift, day in [
            (1, False, "day", 28),
            (2, False, "day", 28),
            (3, True, "night", 27),
        ]:
            session.add(
                Batch(
                    id=number,
                    batch_number=number,
                    is_closed=closed,
                    shift=shift,
                    batch_date=date(2026, 9, day),
                    work_center_id=1,
                    task_description="Test",
                    team="A",
                    nomenclature="Part",
                    ekn_code="E1",
                    shift_start=datetime(2026, 9, day, 8, tzinfo=UTC),
                    shift_end=datetime(2026, 9, day, 16, tzinfo=UTC),
                )
            )
        session.commit()
        # Execute real SQL locally; adapt the session's two calls to the async interface.
        self.repository = BatchRepository(
            SimpleNamespace(
                execute=AsyncMock(side_effect=session.execute),
                scalar=AsyncMock(side_effect=session.scalar),
            )
        )

    async def test_pagination_does_not_change_count_or_export(self):
        filters = BatchFilters(is_closed=False, shift="day")
        page = await self.repository.find_by_filters(filters=filters, offset=1, limit=1)
        total = await self.repository.count_by_filters(filters=filters)
        exported = await self.repository.list_for_export(filters=filters)
        self.assertEqual([row.id for row in page], [1])
        self.assertEqual(total, 2)
        self.assertEqual([row.id for row in exported], [2, 1])

    async def test_each_filter_and_combined_filters(self):
        cases = [
            (BatchFilters(), [2, 1, 3]),
            (BatchFilters(is_closed=True), [3]),
            (BatchFilters(batch_number=1), [1]),
            (BatchFilters(batch_date=date(2026, 9, 27)), [3]),
            (BatchFilters(work_center_id=2), []),
            (BatchFilters(shift="night"), [3]),
            (BatchFilters(date_from=date(2026, 9, 28)), [2, 1]),
            (BatchFilters(date_to=date(2026, 9, 27)), [3]),
            (
                BatchFilters(date_from=date(2026, 9, 27), date_to=date(2026, 9, 28)),
                [2, 1, 3],
            ),
            (BatchFilters(False, 2, date(2026, 9, 28), 1, "day"), [2]),
            (BatchFilters(is_closed=False, shift="night"), []),
        ]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                page = await self.repository.find_by_filters(
                    filters=filters, offset=0, limit=20
                )
                exported = await self.repository.list_for_export(filters=filters)
                total = await self.repository.count_by_filters(filters=filters)
                self.assertEqual([row.id for row in page], expected)
                self.assertEqual([row.id for row in exported], expected)
                self.assertEqual(total, len(expected))


class BatchFilterCacheTests(IsolatedAsyncioTestCase):
    async def test_key_preserves_existing_format_and_separates_queries(self):
        cache = BatchListCache(AsyncMock(get=AsyncMock(return_value="v1")), 60)
        filters = BatchFilters(False, 2, date(2026, 9, 28), 1, "день")
        key = await cache.make_key(filters=filters, offset=0, limit=20)
        old_payload = json.dumps(
            [False, 0, 20, 2, "2026-09-28", 1, "день"], ensure_ascii=False
        )
        self.assertEqual(
            key, f"batch-list:v1:{hashlib.sha256(old_payload.encode()).hexdigest()}"
        )
        for field in (
            "is_closed",
            "batch_number",
            "batch_date",
            "work_center_id",
            "shift",
        ):
            with self.subTest(field=field):
                other = await cache.make_key(
                    filters=replace(filters, **{field: None}), offset=0, limit=20
                )
                self.assertNotEqual(key, other)
        self.assertNotEqual(
            key, await cache.make_key(filters=filters, offset=1, limit=20)
        )
        self.assertNotEqual(
            key, await cache.make_key(filters=filters, offset=0, limit=10)
        )


class BatchFilterApiTests(TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.service = SimpleNamespace(list_batches=AsyncMock(return_value=([], 0)))
        app.dependency_overrides[get_batch_service] = lambda: self.service
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_list_builds_typed_filters_and_keeps_pagination_separate(self):
        response = self.client.get(
            "/batches",
            params={
                "is_closed": "false",
                "batch_number": 2,
                "batch_date": "2026-09-28",
                "work_center_id": 1,
                "shift": "day",
                "offset": 3,
                "limit": 5,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.service.list_batches.assert_awaited_once_with(
            filters=BatchFilters(False, 2, date(2026, 9, 28), 1, "day"),
            offset=3,
            limit=5,
        )
        self.assertEqual(
            response.json(), {"items": [], "total": 0, "offset": 3, "limit": 5}
        )

    def test_invalid_filters_are_rejected_on_list_and_export(self):
        for method, path in [("GET", "/batches"), ("POST", "/batches/export/csv")]:
            for params in [
                {"batch_number": 0},
                {"work_center_id": 0},
                {"batch_date": "invalid"},
                {"shift": ""},
                {"shift": "x" * 51},
                {"is_closed": "invalid"},
            ]:
                with self.subTest(method=method, params=params):
                    self.assertEqual(
                        self.client.request(method, path, params=params).status_code,
                        422,
                    )

    def test_export_keeps_json_safe_task_arguments(self):
        with patch("src.api.v1.routers.batches.export_batches_csv_task.delay") as delay:
            delay.return_value.id = "task-1"
            response = self.client.post(
                "/batches/export/csv",
                params={
                    "is_closed": "false",
                    "batch_date": "2026-09-28",
                    "shift": "day",
                },
            )
        self.assertEqual(response.status_code, 202)
        delay.assert_called_once_with(
            is_closed=False,
            batch_number=None,
            batch_date="2026-09-28",
            work_center_id=None,
            shift="day",
        )

    def test_worker_restores_typed_filters_from_existing_task_format(self):
        with patch(
            "src.tasks.batch_tasks._export_batches_csv", new_callable=AsyncMock
        ) as export:
            export.return_value = {"report_id": "report-1"}
            result = export_batches_csv.run(
                is_closed=False,
                batch_number=None,
                batch_date="2026-09-28",
                work_center_id=None,
                shift="day",
            )
        export.assert_awaited_once_with(
            BatchFilters(is_closed=False, batch_date=date(2026, 9, 28), shift="day")
        )
        self.assertEqual(result, {"report_id": "report-1"})
