import asyncio
from fnmatch import fnmatch
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from scripts.expire_cache_generations import expire_legacy_generations
from src.application.dto import BatchFilters
from src.application.dto.analytics import BatchAnalyticsSnapshot
from src.application.services.batch_analytics_service import BatchAnalyticsService
from src.application.services.batch_service import BatchService
from src.application.services.work_center_service import WorkCenterService
from src.domain.exceptions.batch import BatchNotFoundError
from src.domain.exceptions.work_center import WorkCenterNotFoundError
from src.storage.analytics_cache import AnalyticsCache
from src.storage.batch_details_cache import BatchDetailsCache
from src.storage.batch_list_cache import BatchListCache
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.cache_generation import read_generation
from src.storage.dashboard_cache import DashboardCache
from src.storage.work_center_cache import WorkCenterCache


class ExpiringRedis:
    def __init__(self):
        self.values = {}
        self.deadlines = {}
        self.now = 0

    def purge(self):
        for key, deadline in list(self.deadlines.items()):
            if deadline <= self.now:
                self.values.pop(key, None)
                self.deadlines.pop(key)

    async def get(self, key):
        self.purge()
        return self.values.get(key)

    async def set(self, key, value, *, nx=False, ex=None):
        self.purge()
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.deadlines.pop(key, None)
        if ex is not None:
            self.deadlines[key] = self.now + ex
        return True

    async def expire(self, key, seconds, *, nx=False):
        self.purge()
        if key not in self.values or nx and key in self.deadlines:
            return False
        self.deadlines[key] = self.now + seconds
        return True

    async def scan_iter(self, *, match, count):
        self.purge()
        for key in list(self.values):
            if fnmatch(key, match):
                yield key


CASES = [
    (BatchDetailsCache, "batch-details:v3:999:generation"),
    (WorkCenterCache, "work-center:v2:999:generation"),
    (BatchStatisticsCache, "batch-statistics:v2:999:generation"),
    (DashboardCache, "dashboard-summary:version"),
    (BatchListCache, "batch-list:version"),
]


async def make_key(cache):
    if isinstance(cache, DashboardCache):
        return await cache.make_key(batch_date=None, work_center_id=None, shift=None)
    if isinstance(cache, BatchListCache):
        return await cache.make_key(filters=BatchFilters(), offset=0, limit=20)
    return await cache.make_key(999)


@pytest.mark.parametrize("factory,generation_key", CASES)
def test_generation_expires_and_late_fill_cannot_become_current(
    factory, generation_key
):
    async def scenario():
        redis = ExpiringRedis()
        cache = factory(redis, 10)
        old_key = await make_key(cache)
        assert redis.deadlines[generation_key] == 20
        redis.now = 5
        assert await make_key(cache) == old_key
        assert redis.deadlines[generation_key] == 20
        redis.now = 21
        current_key = await make_key(cache)
        assert current_key != old_key
        # SQL from the old request returns after generation expiry.
        await redis.set(old_key, "stale", ex=100)
        assert await redis.get(current_key) is None
        assert await make_key(cache) == current_key
        if isinstance(cache, (DashboardCache, BatchListCache)):
            await cache.invalidate()
        else:
            await cache.invalidate(999)
        assert redis.deadlines[generation_key] == 41
        assert await make_key(cache) != current_key

    asyncio.run(scenario())


@pytest.mark.parametrize("factory,generation_key", CASES)
def test_legacy_key_gets_ttl_without_changing_token(factory, generation_key):
    async def scenario():
        redis = ExpiringRedis()
        await redis.set(generation_key, "legacy")
        cache = factory(redis, 10)
        key = await make_key(cache)
        assert await redis.get(generation_key) == "legacy"
        assert redis.deadlines[generation_key] == 20
        redis.now = 3
        assert await make_key(cache) == key
        assert redis.deadlines[generation_key] == 20

    asyncio.run(scenario())


def test_missing_records_do_not_create_generation_keys():
    async def scenario():
        redis = ExpiringRedis()
        uow = SimpleNamespace(
            batches=SimpleNamespace(
                get_with_products=AsyncMock(return_value=None),
                get_statistics=AsyncMock(return_value=None),
            ),
            work_centers=SimpleNamespace(get_by_id=AsyncMock(return_value=None)),
            analytics=SimpleNamespace(batch_snapshots=AsyncMock(return_value=[])),
        )
        batches = BatchService(
            uow,
            BatchStatisticsCache(redis, 10),
            None,
            None,
            BatchDetailsCache(redis, 10),
            None,
        )
        center = WorkCenterService(uow, WorkCenterCache(redis, 10))
        analytics = BatchAnalyticsService(
            uow, AnalyticsCache(redis, BatchAnalyticsSnapshot, 10)
        )
        for read, error in [
            (batches.get_by_id, BatchNotFoundError),
            (batches.get_statistics, BatchNotFoundError),
            (center.get_by_id, WorkCenterNotFoundError),
            (analytics.get_statistics, BatchNotFoundError),
        ]:
            with pytest.raises(error):
                await read(999)
        assert redis.values == {}
        assert redis.deadlines == {}

    asyncio.run(scenario())


def test_expiry_repair_does_not_change_concurrent_invalidation_ttl():
    class RotatingRedis(ExpiringRedis):
        async def expire(self, key, seconds, *, nx=False):
            await self.set(key, "new", ex=100)
            return await super().expire(key, seconds, nx=nx)

    async def scenario():
        redis = RotatingRedis()
        await redis.set("generation", "old")
        assert await read_generation(redis, "generation", 10) == "old"
        assert await redis.get("generation") == "new"
        assert redis.deadlines["generation"] == 100

    asyncio.run(scenario())


def test_migration_expires_only_persistent_generation_keys():
    async def scenario():
        redis = ExpiringRedis()
        await redis.set("batch-details:v2:1:generation", "old")
        await redis.set("batch-details:v3:2:generation", "current", ex=50)
        await redis.set("batch-details:v3:2:data:current", "data", ex=40)
        await redis.set("unrelated", "keep")
        patterns = {"batch-details:v*:*:generation": 10}
        assert await expire_legacy_generations(redis, patterns) == 1
        assert await expire_legacy_generations(redis, patterns) == 0
        assert redis.deadlines["batch-details:v2:1:generation"] == 20
        assert redis.deadlines["batch-details:v3:2:generation"] == 50
        assert redis.deadlines["batch-details:v3:2:data:current"] == 40
        assert "unrelated" not in redis.deadlines
        assert await redis.get("batch-details:v2:1:generation") == "old"

    asyncio.run(scenario())


def test_redis_expiry_failure_falls_back_for_http_but_strict_refresh_raises():
    async def scenario():
        client = AsyncMock(
            get=AsyncMock(return_value="legacy"),
            expire=AsyncMock(side_effect=RedisError("offline")),
        )
        assert await BatchDetailsCache(client, 10).make_key(1) is None
        assert await WorkCenterCache(client, 10).make_key(1) is None
        statistics = BatchStatisticsCache(client, 10)
        assert await statistics.make_key(1) is None
        with pytest.raises(RedisError):
            await statistics.make_key(1, strict=True)
        dashboard = DashboardCache(client, 10)
        assert await make_key(dashboard) is None
        with pytest.raises(RedisError):
            await dashboard.make_key(
                batch_date=None, work_center_id=None, shift=None, strict=True
            )
        assert await make_key(BatchListCache(client, 10)) is None

    asyncio.run(scenario())


def test_cold_read_after_update_cannot_publish_snapshot_from_before_generation():
    from tests.unit.test_batch_details_cache import batch

    async def scenario():
        redis = ExpiringRedis()
        cache = BatchDetailsCache(redis, 10)
        current = batch(is_closed=False)

        async def get_row(batch_id):
            nonlocal current
            old = current
            current = batch(is_closed=True)
            # A writer commits while the initial SQL read is in flight.
            await cache.invalidate(batch_id)
            return old

        repo = SimpleNamespace(get_with_products=AsyncMock(side_effect=get_row))
        service = BatchService(
            SimpleNamespace(batches=repo), None, None, None, cache, None
        )
        first = await service.get_by_id(42)
        assert first.is_closed is False
        assert not any(":data:" in key for key in redis.values)
        repo.get_with_products.side_effect = None
        repo.get_with_products.return_value = current
        second = await service.get_by_id(42)
        third = await service.get_by_id(42)
        assert second.is_closed is True
        assert third["is_closed"] is True
        assert repo.get_with_products.await_count == 2

    asyncio.run(scenario())
