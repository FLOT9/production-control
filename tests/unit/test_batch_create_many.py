from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.dto import BatchIntegrationData
from src.application.services.batch_service import BatchService
from src.data.models import Batch, WorkCenter
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import (
    BatchAlreadyExistsError,
    BatchInvalidShiftPeriodError,
)


def integration_item(number: int, **changes) -> BatchIntegrationData:
    return replace(
        BatchIntegrationData(
            is_closed=False,
            task_description="Выпуск деталей",
            work_center_name="Линия 1",
            work_center_identifier="WC-1",
            shift="Дневная",
            team="Бригада 1",
            batch_number=number,
            batch_date=date(2026, 9, 30),
            nomenclature="Деталь",
            ekn_code="EKN-1",
            shift_start=datetime(2026, 9, 30, 3, tzinfo=UTC),
            shift_end=datetime(2026, 9, 30, 15, tzinfo=UTC),
        ),
        **changes,
    )


class BatchCreateManyTests(IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        WorkCenter.__table__.create(engine)
        Batch.__table__.create(engine)
        self.session = Session(engine, expire_on_commit=False)
        self.addCleanup(self.session.close)
        self.operations = []

        def commit():
            self.session.commit()
            self.operations.append("commit")

        adapter = SimpleNamespace(
            add=self.session.add,
            scalar=AsyncMock(side_effect=self.session.scalar),
            execute=AsyncMock(side_effect=self.session.execute),
            get=AsyncMock(side_effect=self.session.get),
            flush=AsyncMock(side_effect=self.session.flush),
            refresh=AsyncMock(side_effect=self.session.refresh),
            commit=AsyncMock(side_effect=commit),
            rollback=AsyncMock(side_effect=self.session.rollback),
        )
        self.adapter = adapter
        self.uow = UnitOfWork(adapter)
        self.dashboard_cache = SimpleNamespace(
            invalidate=AsyncMock(
                side_effect=lambda: self.operations.append("dashboard")
            )
        )
        self.list_cache = SimpleNamespace(
            invalidate=AsyncMock(side_effect=lambda: self.operations.append("list"))
        )
        self.events = SimpleNamespace(create_deliveries=AsyncMock())
        self.service = BatchService(
            self.uow, None, self.dashboard_cache, self.list_cache, None, self.events
        )

    async def test_two_batches_share_one_center_and_commit_before_invalidation(self):
        batches = await self.service.create_many(
            [integration_item(1), integration_item(2)]
        )
        self.assertEqual([batch.batch_number for batch in batches], [1, 2])
        self.assertEqual(batches[0].work_center_id, batches[1].work_center_id)
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(WorkCenter)), 1
        )
        self.adapter.commit.assert_awaited_once()
        self.adapter.rollback.assert_not_awaited()
        self.assertEqual(self.operations, ["commit", "dashboard", "list"])
        self.assertEqual(self.events.create_deliveries.await_count, 2)

    async def test_second_duplicate_rolls_back_first_batch_and_new_center(self):
        with self.assertRaises(BatchAlreadyExistsError):
            await self.service.create_many([integration_item(1), integration_item(1)])
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(Batch)), 0
        )
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(WorkCenter)), 0
        )
        self.adapter.commit.assert_not_awaited()
        self.adapter.rollback.assert_awaited_once()
        self.assertEqual(self.operations, [])

    async def test_initial_closed_status_is_saved(self):
        batch = (await self.service.create_many([integration_item(1, is_closed=True)]))[
            0
        ]
        self.assertTrue(batch.is_closed)
        self.assertIsNotNone(batch.closed_at)
        event = self.events.create_deliveries.await_args.args[0]
        self.assertTrue(event.data["is_closed"])

    async def test_invalid_period_rolls_back_created_center(self):
        item = integration_item(1)
        with self.assertRaises(BatchInvalidShiftPeriodError):
            await self.service.create_many([replace(item, shift_end=item.shift_start)])
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(WorkCenter)), 0
        )
        self.adapter.commit.assert_not_awaited()

    async def test_event_failure_rolls_back_all_batches(self):
        self.events.create_deliveries.side_effect = [
            [],
            RuntimeError("delivery failure"),
        ]
        with self.assertRaisesRegex(RuntimeError, "delivery failure"):
            await self.service.create_many([integration_item(1), integration_item(2)])
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(Batch)), 0
        )
        self.adapter.commit.assert_not_awaited()
        self.assertEqual(self.operations, [])

    async def test_database_unique_conflict_is_translated_and_rolled_back(self):
        self.uow.batches.create = AsyncMock(
            side_effect=IntegrityError("insert", {}, RuntimeError("unique conflict"))
        )
        with self.assertRaises(BatchAlreadyExistsError):
            await self.service.create_many([integration_item(1)])
        self.adapter.rollback.assert_awaited_once()
        self.adapter.commit.assert_not_awaited()

    async def test_single_creation_still_commits_and_creates_an_open_batch(self):
        center = await self.uow.work_centers.get_or_create_by_identifier(
            "WC-1", "Line 1"
        )
        item = integration_item(1)
        batch = await self.service.create(
            task_description=item.task_description,
            work_center_id=center.id,
            shift=item.shift,
            team=item.team,
            batch_number=item.batch_number,
            batch_date=item.batch_date,
            nomenclature=item.nomenclature,
            ekn_code=item.ekn_code,
            shift_start=item.shift_start,
            shift_end=item.shift_end,
        )
        self.assertFalse(batch.is_closed)
        self.assertIsNone(batch.closed_at)
        self.assertEqual(self.operations, ["commit", "dashboard", "list"])
