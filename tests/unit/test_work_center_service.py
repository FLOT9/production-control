from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

from sqlalchemy.exc import IntegrityError

from src.application.services.work_center_service import WorkCenterService
from src.domain.exceptions.work_center import (
    WorkCenterAlreadyExistsError,
    WorkCenterHasBatchesError,
    WorkCenterNotFoundError,
)


class WorkCenterServiceTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.center = SimpleNamespace(
            id=1,
            identifier="WC-1",
            name="Workshop",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        self.uow = SimpleNamespace(
            work_centers=SimpleNamespace(
                get_by_id=AsyncMock(return_value=self.center),
                get_by_identifier=AsyncMock(return_value=None),
                create=AsyncMock(return_value=self.center),
                delete=AsyncMock(),
            ),
            batches=SimpleNamespace(
                exists_by_work_center_id=AsyncMock(return_value=False)
            ),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )
        self.cache = SimpleNamespace(
            make_key=AsyncMock(return_value="work-center:v2:1:data:test"),
            get=AsyncMock(return_value=None),
            set=AsyncMock(),
            invalidate=AsyncMock(),
        )
        self.service = WorkCenterService(self.uow, self.cache)

    async def test_create_and_duplicate(self):
        self.assertIs(await self.service.create("WC-1", "Workshop"), self.center)
        self.uow.commit.assert_awaited_once()
        self.uow.work_centers.get_by_identifier.return_value = self.center
        with self.assertRaises(WorkCenterAlreadyExistsError):
            await self.service.create("WC-1", "Workshop")
        self.uow.work_centers.create.assert_awaited_once()
        self.uow.commit.assert_awaited_once()

    async def test_unique_constraint_race_returns_domain_conflict(self):
        self.uow.work_centers.create.side_effect = IntegrityError(
            "unique violation", {}, Exception()
        )

        with self.assertRaises(WorkCenterAlreadyExistsError):
            await self.service.create("WC-1", "Workshop")

        self.uow.rollback.assert_awaited_once()
        self.uow.commit.assert_not_awaited()

    async def test_cache_hit_avoids_database(self):
        self.cache.get.return_value = {"id": 1}
        self.assertEqual(await self.service.get_by_id(1), {"id": 1})
        self.uow.work_centers.get_by_id.assert_not_awaited()

    async def test_cache_miss_serializes_and_caches_database_result(self):
        result = await self.service.get_by_id(1)
        self.assertEqual(result["identifier"], "WC-1")
        self.assertEqual(result["created_at"], self.center.created_at.isoformat())
        self.cache.set.assert_awaited_once_with("work-center:v2:1:data:test", 1, result)

    async def test_missing_center_is_not_cached(self):
        self.uow.work_centers.get_by_id.return_value = None
        with self.assertRaises(WorkCenterNotFoundError):
            await self.service.get_by_id(1)
        self.cache.set.assert_not_awaited()

    async def test_delete_uses_database_and_invalidates_after_commit(self):
        order = Mock()
        order.attach_mock(self.uow.work_centers.delete, "delete")
        order.attach_mock(self.uow.commit, "commit")
        order.attach_mock(self.cache.invalidate, "invalidate")
        self.cache.get.return_value = {"id": 1}
        await self.service.delete(1)
        self.uow.work_centers.delete.assert_awaited_once_with(self.center)
        self.cache.get.assert_not_awaited()
        self.assertEqual(
            [call[0] for call in order.mock_calls], ["delete", "commit", "invalidate"]
        )

    async def test_related_batches_block_deletion(self):
        self.uow.batches.exists_by_work_center_id.return_value = True
        with self.assertRaises(WorkCenterHasBatchesError):
            await self.service.delete(1)
        self.uow.work_centers.delete.assert_not_awaited()
        self.uow.commit.assert_not_awaited()
        self.cache.invalidate.assert_not_awaited()

    async def test_missing_center_blocks_deletion_even_with_cached_value(self):
        self.cache.get.return_value = {"id": 1}
        self.uow.work_centers.get_by_id.return_value = None
        with self.assertRaises(WorkCenterNotFoundError):
            await self.service.delete(1)
        self.uow.work_centers.delete.assert_not_awaited()
        self.uow.commit.assert_not_awaited()
        self.cache.invalidate.assert_not_awaited()

    async def test_failed_commit_preserves_cache(self):
        self.uow.commit.side_effect = RuntimeError("commit failed")
        with self.assertRaises(RuntimeError):
            await self.service.delete(1)
        self.cache.invalidate.assert_not_awaited()
