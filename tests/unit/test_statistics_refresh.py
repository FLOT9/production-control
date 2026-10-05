import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from redis.exceptions import RedisError

from src.application.dto import BatchProductCounts
from src.application.dto.dashboard import DashboardCounts
from src.application.services.batch_service import BatchService
from src.application.services.dashboard_service import DashboardService
from src.application.services.statistics_refresh_service import StatisticsRefreshService
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache
from src.tasks.analytics_tasks import (
    _update_cached_statistics,
    update_cached_statistics,
)
from src.tasks.celery_app import celery_app
from tests.unit.test_other_cache_generations import FakeRedis


def batch_service(repository, cache):
    return BatchService(
        SimpleNamespace(batches=repository), cache, None, None, None, None
    )


class StatisticsRefreshTests(IsolatedAsyncioTestCase):
    async def test_refresh_replaces_cached_counts_from_database(self):
        cache = BatchStatisticsCache(FakeRedis(), ttl_seconds=300)
        repository = SimpleNamespace(
            get_statistics_many=AsyncMock(return_value=[BatchProductCounts(1, 10, 2)])
        )
        service = batch_service(repository, cache)
        self.assertEqual(await service.refresh_statistics([1]), 1)
        repository.get_statistics_many.return_value = [BatchProductCounts(1, 10, 8)]
        self.assertEqual(await service.refresh_statistics([1]), 1)
        cached = await cache.get(await cache.make_key(1), 1)
        self.assertEqual(cached.aggregated_products, 8)
        self.assertEqual(cached.pending_products, 2)
        self.assertEqual(cached.aggregation_percent, 80)

    async def test_late_refresh_cannot_fill_generation_after_invalidation(self):
        cache = BatchStatisticsCache(FakeRedis(), ttl_seconds=300)
        started = asyncio.Event()
        resume = asyncio.Event()

        async def read(_ids):
            started.set()
            await resume.wait()
            return [BatchProductCounts(1, 10, 2)]

        service = batch_service(SimpleNamespace(get_statistics_many=read), cache)
        old_key = await cache.make_key(1)
        refresh = asyncio.create_task(service.refresh_statistics([1]))
        await started.wait()
        await cache.invalidate(1)
        resume.set()
        await refresh
        self.assertIsNotNone(await cache.get(old_key, 1))
        self.assertIsNone(await cache.get(await cache.make_key(1), 1))

    async def test_deleted_between_selection_and_counting_is_skipped(self):
        cache = BatchStatisticsCache(FakeRedis(), ttl_seconds=300)
        repository = SimpleNamespace(
            get_statistics_many=AsyncMock(return_value=[BatchProductCounts(1, 0, 0)])
        )
        self.assertEqual(
            await batch_service(repository, cache).refresh_statistics([1, 2]), 1
        )
        self.assertIsNone(await cache.get(await cache.make_key(2), 2))

    async def test_redis_read_failure_is_visible_to_background_task(self):
        client = AsyncMock(get=AsyncMock(side_effect=RedisError("unavailable")))
        repository = SimpleNamespace(get_statistics_many=AsyncMock())
        service = batch_service(repository, BatchStatisticsCache(client, 300))
        with self.assertRaises(RedisError):
            await service.refresh_statistics([1])
        repository.get_statistics_many.assert_not_awaited()

    async def test_redis_pipeline_failure_is_not_reported_as_success(self):
        client = AsyncMock(get=AsyncMock(return_value="v1"))
        pipeline = MagicMock()
        pipeline.__aenter__ = AsyncMock(return_value=pipeline)
        pipeline.__aexit__ = AsyncMock(return_value=None)
        pipeline.execute = AsyncMock(side_effect=RedisError("write failure"))
        client.pipeline = MagicMock(return_value=pipeline)
        repository = SimpleNamespace(
            get_statistics_many=AsyncMock(return_value=[BatchProductCounts(1, 10, 2)])
        )
        with self.assertRaises(RedisError):
            await batch_service(
                repository, BatchStatisticsCache(client, 300)
            ).refresh_statistics([1])

    async def test_dashboard_refresh_ignores_saved_value_and_reuses_formulas(self):
        cache = DashboardCache(FakeRedis(), ttl_seconds=300)
        repository = SimpleNamespace(
            get_summary=AsyncMock(return_value=DashboardCounts(2, 1, 10, 2))
        )
        service = DashboardService(SimpleNamespace(dashboard=repository), cache)
        await service.get_summary()
        repository.get_summary.return_value = DashboardCounts(2, 1, 10, 8)
        refreshed = await service.refresh_summary()
        self.assertEqual(refreshed.aggregation_percent, 80)
        self.assertEqual(await service.get_summary(), refreshed)
        self.assertEqual(repository.get_summary.await_count, 2)

    async def test_dashboard_write_failure_propagates_only_in_strict_mode(self):
        client = AsyncMock(
            get=AsyncMock(return_value="v1"),
            set=AsyncMock(side_effect=RedisError("write failure")),
        )
        cache = DashboardCache(client, ttl_seconds=300)
        repository = SimpleNamespace(
            get_summary=AsyncMock(return_value=DashboardCounts(0, 0, 0, 0))
        )
        service = DashboardService(SimpleNamespace(dashboard=repository), cache)
        with self.assertRaises(RedisError):
            await service.refresh_summary()
        summary = await service._read_summary(
            batch_date=None, work_center_id=None, shift=None
        )
        await cache.set("key", summary)

    async def test_pages_and_two_dashboards_are_refreshed(self):
        repository = SimpleNamespace(list_ids=AsyncMock(side_effect=[[1, 2], [4], []]))
        uow = SimpleNamespace(batches=repository, rollback=AsyncMock())
        batches = SimpleNamespace(refresh_statistics=AsyncMock(side_effect=[2, 1]))
        dashboard = SimpleNamespace(refresh_summary=AsyncMock())
        service = StatisticsRefreshService(uow, batches, dashboard)
        today = date(2026, 10, 1)
        self.assertEqual(
            await service.refresh_all(today=today, page_size=2),
            {"batches_updated": 3, "dashboards_updated": 2},
        )
        self.assertEqual(
            [call.kwargs["after_id"] for call in repository.list_ids.await_args_list],
            [0, 2, 4],
        )
        self.assertEqual(uow.rollback.await_count, 2)
        self.assertEqual(dashboard.refresh_summary.await_args_list[0].kwargs, {})
        self.assertEqual(
            dashboard.refresh_summary.await_args_list[1].kwargs, {"batch_date": today}
        )

    async def test_empty_database_still_refreshes_dashboards(self):
        uow = SimpleNamespace(
            batches=SimpleNamespace(list_ids=AsyncMock(return_value=[]))
        )
        batches = SimpleNamespace(refresh_statistics=AsyncMock())
        dashboard = SimpleNamespace(refresh_summary=AsyncMock())
        result = await StatisticsRefreshService(uow, batches, dashboard).refresh_all(
            today=date(2026, 10, 1)
        )
        self.assertEqual(result, {"batches_updated": 0, "dashboards_updated": 2})
        batches.refresh_statistics.assert_not_awaited()


class StatisticsRefreshTaskTests(IsolatedAsyncioTestCase):
    async def test_task_uses_production_date_and_closes_resources_on_failure(self):
        client = SimpleNamespace(aclose=AsyncMock())
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=object())
        context.__aexit__ = AsyncMock(return_value=None)
        service = SimpleNamespace(
            refresh_all=AsyncMock(side_effect=RedisError("failed"))
        )
        with (
            patch("src.tasks.analytics_tasks.create_redis_client", return_value=client),
            patch(
                "src.tasks.analytics_tasks.async_session_maker", return_value=context
            ),
            patch("src.tasks.analytics_tasks.UnitOfWork"),
            patch("src.tasks.analytics_tasks.build_batch_service"),
            patch(
                "src.tasks.analytics_tasks.StatisticsRefreshService",
                return_value=service,
            ),
            patch("src.tasks.analytics_tasks.datetime") as clock,
            patch(
                "src.tasks.analytics_tasks.settings.production_timezone",
                "Asia/Yekaterinburg",
            ),
            patch(
                "src.tasks.analytics_tasks.dispose_engine", new_callable=AsyncMock
            ) as dispose,
            self.assertRaises(RedisError),
        ):
            clock.now.return_value = datetime(2026, 10, 1, 1, tzinfo=UTC)
            await _update_cached_statistics()
        clock.now.assert_called_once_with(ZoneInfo("Asia/Yekaterinburg"))
        service.refresh_all.assert_awaited_once_with(today=date(2026, 10, 1))
        client.aclose.assert_awaited_once()
        dispose.assert_awaited_once()


class StatisticsRefreshScheduleTests(TestCase):
    def test_five_minute_schedule_matches_registered_task(self):
        entry = celery_app.conf.beat_schedule["update-cached-statistics"]
        self.assertEqual(entry["task"], update_cached_statistics.name)
        self.assertEqual(entry["schedule"].minute, set(range(0, 60, 5)))
        self.assertIn("src.tasks.analytics_tasks", celery_app.conf.include)
