from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.application.dto.batch_statistics import BatchProductCounts
from src.application.events import WebhookEventType
from src.application.services.batch_service import BatchService
from src.data.models import Batch, WorkCenter
from src.data.repositories.batch_repository import BatchRepository
from src.tasks.batch_tasks import (
    _auto_close_expired_batches,
    auto_close_expired_batches,
)
from src.tasks.celery_app import celery_app

CUTOFF = datetime(2026, 9, 30, 20, tzinfo=UTC)


def batch(batch_id=1, *, closed=False, end=None):
    return Batch(
        id=batch_id,
        is_closed=closed,
        closed_at=CUTOFF if closed else None,
        work_center_id=1,
        batch_number=batch_id,
        batch_date=date(2026, 9, 30),
        task_description="Task",
        shift="Day",
        team="A",
        nomenclature="Part",
        ekn_code="EKN",
        shift_start=CUTOFF - timedelta(hours=12),
        shift_end=end or CUTOFF - timedelta(hours=1),
    )


class AutoCloseServiceTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.row = batch()
        self.operations = []
        self.uow = SimpleNamespace(
            batches=SimpleNamespace(
                get_by_id_for_update=AsyncMock(return_value=self.row),
                refresh=AsyncMock(),
                get_statistics=AsyncMock(return_value=BatchProductCounts(1, 3, 2)),
            ),
            commit=AsyncMock(side_effect=lambda: self.operations.append("commit")),
            rollback=AsyncMock(),
        )
        self.events = SimpleNamespace(
            create_deliveries=AsyncMock(
                side_effect=lambda _: self.operations.append("event")
            )
        )

        def cache(name):
            return SimpleNamespace(
                invalidate=AsyncMock(
                    side_effect=lambda *_: self.operations.append(name)
                )
            )

        self.service = BatchService(
            self.uow,
            cache("statistics"),
            cache("dashboard"),
            cache("list"),
            cache("details"),
            self.events,
        )

    async def test_expired_batch_closes_once_with_event_and_post_commit_invalidation(
        self,
    ):
        self.assertTrue(await self.service.close_if_expired(1, CUTOFF))
        self.assertTrue(self.row.is_closed)
        self.assertIsNotNone(self.row.closed_at)
        self.assertEqual(
            self.operations,
            ["event", "commit", "dashboard", "list", "statistics", "details"],
        )
        event = self.events.create_deliveries.await_args.args[0]
        self.assertEqual(event.event_type, WebhookEventType.BATCH_CLOSED)
        self.assertEqual(event.data["statistics"]["aggregation_percent"], 66.67)
        self.assertEqual(
            event.data["changes"]["is_closed"], {"old": False, "new": True}
        )
        self.assertFalse(await self.service.close_if_expired(1, CUTOFF))
        self.events.create_deliveries.assert_awaited_once()
        self.uow.commit.assert_awaited_once()

    async def test_extended_or_not_yet_expired_shift_is_skipped_after_lock(self):
        for end in [CUTOFF, CUTOFF + timedelta(hours=1)]:
            with self.subTest(end=end):
                self.row.shift_end = end
                self.assertFalse(await self.service.close_if_expired(1, CUTOFF))
                self.assertFalse(self.row.is_closed)
        self.events.create_deliveries.assert_not_awaited()
        self.uow.commit.assert_not_awaited()
        self.assertEqual(self.uow.rollback.await_count, 2)

    async def test_deleted_batch_is_skipped(self):
        self.uow.batches.get_by_id_for_update.return_value = None
        self.assertFalse(await self.service.close_if_expired(1, CUTOFF))
        self.uow.rollback.assert_awaited_once()
        self.events.create_deliveries.assert_not_awaited()

    async def test_event_failure_rolls_back_and_does_not_invalidate(self):
        self.events.create_deliveries.side_effect = RuntimeError("event failure")
        with self.assertRaisesRegex(RuntimeError, "event failure"):
            await self.service.close_if_expired(1, CUTOFF)
        self.uow.rollback.assert_awaited_once()
        self.uow.commit.assert_not_awaited()
        self.assertEqual(self.operations, [])

    async def test_manual_update_still_uses_same_closing_flow(self):
        result = await self.service.update(1, {"is_closed": True})
        self.assertTrue(result.is_closed)
        self.assertEqual(
            self.events.create_deliveries.await_args.args[0].event_type,
            WebhookEventType.BATCH_CLOSED,
        )
        self.uow.commit.assert_awaited_once()


class AutoClosePaginationTests(IsolatedAsyncioTestCase):
    async def test_sql_filters_and_cursor_do_not_skip_rows_as_batches_close(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        WorkCenter.__table__.create(engine)
        Batch.__table__.create(engine)
        session = Session(engine)
        self.addCleanup(session.close)
        session.add(WorkCenter(id=1, name="Line", identifier="WC-1"))
        session.add_all(
            [
                batch(1),
                batch(2, closed=True),
                batch(3, end=CUTOFF + timedelta(hours=1)),
                batch(4),
                batch(5, end=CUTOFF),
            ]
        )
        session.commit()
        repository = BatchRepository(
            SimpleNamespace(execute=AsyncMock(side_effect=session.execute))
        )
        uow = SimpleNamespace(batches=repository)
        service = BatchService(uow, None, None, None, None, None)

        async def close(batch_id, expired_before):
            session.get(Batch, batch_id).is_closed = True
            session.commit()
            return True

        service.close_if_expired = AsyncMock(side_effect=close)
        result = await service.close_expired_batches(expired_before=CUTOFF, page_size=1)
        self.assertEqual(result, {"checked": 2, "closed": 2, "skipped": 0})
        self.assertEqual(
            [call.args[0] for call in service.close_if_expired.await_args_list], [1, 4]
        )
        self.assertEqual(
            await service.close_expired_batches(expired_before=CUTOFF, page_size=1),
            {"checked": 0, "closed": 0, "skipped": 0},
        )


class AutoCloseTaskTests(IsolatedAsyncioTestCase):
    async def test_failed_run_closes_redis_and_disposes_engine(self):
        client = SimpleNamespace(aclose=AsyncMock())
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=object())
        context.__aexit__ = AsyncMock(return_value=None)
        service = SimpleNamespace(
            close_expired_batches=AsyncMock(side_effect=RuntimeError("failure"))
        )
        with (
            patch("src.tasks.batch_tasks.create_redis_client", return_value=client),
            patch("src.tasks.batch_tasks.async_session_maker", return_value=context),
            patch("src.tasks.batch_tasks.UnitOfWork"),
            patch("src.tasks.batch_tasks.build_batch_service", return_value=service),
            patch(
                "src.tasks.batch_tasks.dispose_engine", new_callable=AsyncMock
            ) as dispose,
            self.assertRaisesRegex(RuntimeError, "failure"),
        ):
            await _auto_close_expired_batches()
        client.aclose.assert_awaited_once()
        dispose.assert_awaited_once()


class AutoCloseScheduleTests(TestCase):
    def test_registered_task_matches_daily_schedule(self):
        entry = celery_app.conf.beat_schedule["auto-close-expired-batches"]
        self.assertEqual(entry["task"], auto_close_expired_batches.name)
        self.assertEqual(entry["schedule"].hour, {1})
        self.assertEqual(entry["schedule"].minute, {0})
