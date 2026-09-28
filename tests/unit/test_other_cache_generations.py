import asyncio
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Self

from src.application.dto import BatchProductCounts
from src.application.services.batch_service import BatchService
from src.application.services.work_center_service import WorkCenterService
from src.domain.exceptions.work_center import WorkCenterNotFoundError
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.work_center_cache import WorkCenterCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.values.get(key) for key in keys]

    def pipeline(self, *, transaction: bool = False) -> "FakePipeline":
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.pending: list[tuple[str, str]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    def set(self, key: str, value: str, *, ex: int) -> None:
        self.pending.append((key, value))

    async def execute(self) -> None:
        for key, value in self.pending:
            await self.redis.set(key, value)


class OtherCacheGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_deleted_work_center_cannot_be_restored_by_late_read(self) -> None:
        redis = FakeRedis()
        cache = WorkCenterCache(redis, ttl_seconds=60)
        started = asyncio.Event()
        resume = asyncio.Event()
        now = datetime.now(UTC)
        database_row = SimpleNamespace(
            id=1, identifier="WC-1", name="Center", created_at=now, updated_at=now
        )
        reads = 0

        async def get_by_id(_id: int) -> SimpleNamespace | None:
            nonlocal reads
            reads += 1
            row = database_row
            if reads == 1:
                started.set()
                await resume.wait()
            return row

        service = WorkCenterService(
            uow=SimpleNamespace(work_centers=SimpleNamespace(get_by_id=get_by_id)),
            cache=cache,
        )
        old_read = asyncio.create_task(service.get_by_id(1))
        await started.wait()
        old_key = await cache.make_key(1)

        database_row = None
        await cache.invalidate(1)
        resume.set()
        await old_read

        self.assertIn(old_key, redis.values)
        self.assertNotEqual(old_key, await cache.make_key(1))
        with self.assertRaises(WorkCenterNotFoundError):
            await service.get_by_id(1)
        self.assertEqual(reads, 2)

    async def test_bulk_statistics_refetches_only_changed_batch(self) -> None:
        redis = FakeRedis()
        cache = BatchStatisticsCache(redis, ttl_seconds=300)
        started = asyncio.Event()
        resume = asyncio.Event()
        totals = {1: 1, 2: 2}
        requested_ids: list[list[int]] = []

        async def get_statistics_many(ids: list[int]) -> list[BatchProductCounts]:
            requested_ids.append(ids)
            rows = [BatchProductCounts(i, totals[i], 0) for i in ids]
            if len(requested_ids) == 1:
                started.set()
                await resume.wait()
            return rows

        service = BatchService(
            uow=SimpleNamespace(
                batches=SimpleNamespace(get_statistics_many=get_statistics_many)
            ),
            statistics_cache=cache,
            dashboard_cache=None,
            list_cache=None,
            details_cache=None,
            webhook_event_service=None,
        )
        old_read = asyncio.create_task(service.compare_batches([1, 2]))
        await started.wait()
        old_key = await cache.make_key(1)

        totals[1] = 3
        await cache.invalidate(1)
        resume.set()
        await old_read

        self.assertIn(old_key, redis.values)
        self.assertNotEqual(old_key, await cache.make_key(1))
        current = await service.compare_batches([1, 2])
        self.assertEqual([item.total_products for item in current], [3, 2])
        self.assertEqual(requested_ids, [[1, 2], [1]])
