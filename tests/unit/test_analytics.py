from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.api.dependencies.analytics import (
    get_analytics_dashboard_service,
    get_batch_analytics_service,
    get_batch_comparison_service,
)
from src.api.v1.routers.analytics import router
from src.api.v1.routers.batches import router as batches_router
from src.application.analytics.calculator import (
    batch_analytics,
    batch_timeline,
    compare_batches,
)
from src.application.dto.analytics import (
    BatchAnalyticsSnapshot,
    BatchInfo,
    DashboardAnalytics,
)
from src.application.services.analytics_dashboard_service import (
    AnalyticsDashboardService,
)
from src.application.services.batch_analytics_service import BatchAnalyticsService
from src.application.services.batch_comparison_service import BatchComparisonService
from src.data.models import Batch, Product, WorkCenter
from src.data.repositories.analytics_repository import AnalyticsRepository
from src.domain.exceptions.batch import BatchNotFoundError
from src.storage.analytics_cache import AnalyticsCache
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache

START = datetime(2026, 10, 3, 8, tzinfo=UTC)
NOW = START + timedelta(hours=2)


def snapshot(batch_id=1, total=1000, aggregated=400, duration=8):
    return BatchAnalyticsSnapshot(
        batch_info=BatchInfo(
            id=batch_id,
            batch_number=batch_id,
            batch_date=START.date(),
            nomenclature="Bolt",
            work_center_id=1,
            work_center_name="Line",
            shift="Day",
            team="A",
            is_closed=False,
            shift_start=START,
            shift_end=START + timedelta(hours=duration),
            closed_at=None,
        ),
        total_products=total,
        aggregated_products=aggregated,
        window_products=aggregated,
        last_aggregated_at=NOW if aggregated else None,
        observed_at=NOW,
    )


class CalculatorTests(TestCase):
    def test_rate_and_forecast_use_elapsed_time_but_comparison_uses_full_shift(self):
        row = snapshot()
        timeline = batch_timeline(row, NOW)
        self.assertEqual(timeline.products_per_hour, 200)
        self.assertEqual(timeline.estimated_completion_at, NOW + timedelta(hours=3))
        self.assertEqual(timeline.forecast_status, "available")
        comparison = compare_batches(
            [row, snapshot(2, total=200, aggregated=100, duration=2)]
        )
        self.assertEqual(comparison.average.products_per_hour, 50)
        self.assertEqual(comparison.average.aggregation_percent, 45)
        self.assertEqual(comparison.overall_products_per_hour, 50)
        # Weighted and arithmetic rates must differ for unequal durations/rates.
        comparison = compare_batches(
            [row, snapshot(2, total=200, aggregated=200, duration=2)]
        )
        self.assertEqual(comparison.average.products_per_hour, 75)
        self.assertEqual(comparison.overall_products_per_hour, 60)

    def test_forecast_edge_cases(self):
        cases = [
            (snapshot(total=0, aggregated=0), NOW, "no_products", 0),
            (snapshot(aggregated=0), START - timedelta(hours=1), "not_started", None),
            (snapshot(aggregated=0), NOW, "no_progress", 0),
            (snapshot(), START + timedelta(hours=9), "shift_finished", 50),
            (snapshot(total=400), NOW, "completed", 200),
        ]
        for row, now, status, rate in cases:
            with self.subTest(status=status):
                result = batch_timeline(row, now)
                self.assertEqual(result.forecast_status, status)
                self.assertEqual(result.products_per_hour, rate)
                if status != "completed":
                    self.assertIsNone(result.estimated_completion_at)
        row = snapshot()
        row = row.model_copy(
            update={
                "batch_info": row.batch_info.model_copy(
                    update={"is_closed": True, "closed_at": START + timedelta(hours=1)}
                )
            }
        )
        result = batch_timeline(row, NOW)
        self.assertEqual(result.elapsed_hours, 1)
        self.assertEqual(result.forecast_status, "batch_closed")
        self.assertIsNone(result.estimated_completion_at)


class RepositoryTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        for model in [WorkCenter, Batch, Product]:
            model.__table__.create(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        self.session.add_all(
            [
                WorkCenter(id=1, name="First", identifier="A"),
                WorkCenter(id=2, name="Second", identifier="B"),
            ]
        )
        for id_, center, shift, day in [
            (1, 1, "Day", START.date()),
            (2, 1, "Night", START.date()),
            (3, 2, "Day", date(2026, 10, 2)),
        ]:
            self.session.add(
                Batch(
                    id=id_,
                    work_center_id=center,
                    is_closed=id_ == 3,
                    task_description="Task",
                    shift=shift,
                    team="A",
                    batch_number=id_,
                    batch_date=day,
                    nomenclature="Bolt",
                    ekn_code="EKN",
                    shift_start=START,
                    shift_end=START + timedelta(hours=8),
                )
            )
        self.session.add_all(
            [
                Product(
                    unique_code="A",
                    batch_id=1,
                    is_aggregated=True,
                    aggregated_at=START + timedelta(hours=1),
                ),
                Product(
                    unique_code="B",
                    batch_id=1,
                    is_aggregated=True,
                    aggregated_at=START - timedelta(hours=1),
                ),
                Product(unique_code="C", batch_id=1, is_aggregated=False),
                Product(
                    unique_code="D",
                    batch_id=3,
                    is_aggregated=True,
                    aggregated_at=START + timedelta(hours=1),
                ),
            ]
        )
        self.session.commit()
        self.repo = AnalyticsRepository(
            SimpleNamespace(execute=AsyncMock(side_effect=self.session.execute))
        )

    async def test_dashboard_rollups_zero_product_batches_and_filters(self):
        result = await self.repo.dashboard(
            today=START.date(),
            date_from=None,
            date_to=None,
            work_center_id=None,
            shift=None,
        )
        self.assertEqual(result.summary.total_batches, 3)
        self.assertEqual(result.summary.total_products, 4)
        self.assertEqual(result.today.total_batches, 2)
        self.assertEqual(result.today.aggregated_products, 2)
        self.assertEqual(
            [item.work_center_id for item in result.top_work_centers], [1, 2]
        )
        self.assertEqual([item.total_batches for item in result.by_shift], [2, 1])
        result = await self.repo.dashboard(
            today=START.date(),
            date_from=date(2026, 10, 2),
            date_to=date(2026, 10, 2),
            work_center_id=2,
            shift="Day",
        )
        self.assertEqual(result.summary.total_batches, 1)
        self.assertEqual(result.today.total_batches, 0)
        result = await self.repo.dashboard(
            today=START.date(),
            date_from=None,
            date_to=None,
            work_center_id=99,
            shift=None,
        )
        self.assertEqual(result.summary.total_products, 0)
        self.assertEqual(result.top_work_centers, [])

    async def test_snapshot_counts_only_aggregation_within_work_window(self):
        rows = await self.repo.batch_snapshots([1, 2], now=NOW)
        by_id = {row.batch_info.id: row for row in rows}
        self.assertEqual(by_id[1].aggregated_products, 2)
        self.assertEqual(by_id[1].window_products, 1)
        self.assertEqual(batch_analytics(by_id[1], NOW).timeline.products_per_hour, 0.5)
        self.assertEqual(by_id[2].total_products, 0)
        self.assertEqual(by_id[1].batch_info.shift_start.tzinfo, UTC)


class ServiceTests(IsolatedAsyncioTestCase):
    async def test_comparison_preserves_order_and_missing_batch_fails(self):
        uow = SimpleNamespace(
            analytics=SimpleNamespace(
                batch_snapshots=AsyncMock(return_value=[snapshot(1), snapshot(2)])
            )
        )
        result = await BatchComparisonService(uow).compare([2, 1])
        self.assertEqual([item.batch_info.id for item in result.items], [2, 1])
        with self.assertRaises(BatchNotFoundError):
            await BatchComparisonService(uow).compare([1, 3])

    async def test_cached_snapshot_recalculates_time_and_missing_returns_not_found(
        self,
    ):
        cache = SimpleNamespace(
            batch_key=AsyncMock(return_value="key"),
            get=AsyncMock(return_value=snapshot()),
            set=AsyncMock(),
        )
        uow = SimpleNamespace(
            analytics=SimpleNamespace(batch_snapshots=AsyncMock(return_value=[]))
        )
        service = BatchAnalyticsService(uow, cache)
        first = await service.get_statistics(1, now=NOW)
        later = await service.get_statistics(1, now=NOW + timedelta(hours=2))
        self.assertEqual(first.timeline.products_per_hour, 200)
        self.assertEqual(later.timeline.products_per_hour, 100)
        uow.analytics.batch_snapshots.assert_not_awaited()
        cache.get.return_value = None
        with self.assertRaises(BatchNotFoundError):
            await service.get_statistics(99, now=NOW)

    async def test_local_today_and_redis_write_failure(self):
        zero = {
            "total_batches": 0,
            "open_batches": 0,
            "closed_batches": 0,
            "total_products": 0,
            "aggregated_products": 0,
            "pending_products": 0,
            "aggregation_percent": 0,
        }
        dashboard = DashboardAnalytics(
            summary=zero, today=zero, by_shift=[], top_work_centers=[]
        )
        cache = SimpleNamespace(
            dashboard_key=AsyncMock(return_value=None),
            get=AsyncMock(return_value=None),
            set=AsyncMock(return_value=False),
        )
        uow = SimpleNamespace(
            analytics=SimpleNamespace(dashboard=AsyncMock(return_value=dashboard))
        )
        result = await AnalyticsDashboardService(uow, cache).get_dashboard(
            now=datetime(2026, 10, 2, 22, tzinfo=UTC)
        )
        self.assertIsNone(result.cached_at)
        self.assertEqual(
            uow.analytics.dashboard.await_args.kwargs["today"], date(2026, 10, 3)
        )

    async def test_cache_keys_share_mutation_generations_and_separate_days(self):
        values = {}

        async def get(key):
            return values.get(key)

        async def put(key, value, **kwargs):
            if not kwargs.get("nx") or key not in values:
                values[key] = value

        client = SimpleNamespace(
            get=AsyncMock(side_effect=get),
            set=AsyncMock(side_effect=put),
            expire=AsyncMock(return_value=True),
        )
        cache = AnalyticsCache(client, DashboardAnalytics, 300)
        params = {
            "today": START.date(),
            "date_from": None,
            "date_to": None,
            "work_center_id": None,
            "shift": None,
        }
        first = await cache.dashboard_key(**params)
        self.assertNotEqual(
            first, await cache.dashboard_key(**(params | {"today": date(2026, 10, 4)}))
        )
        await DashboardCache(client, 300).invalidate()
        self.assertNotEqual(first, await cache.dashboard_key(**params))
        old = await cache.batch_key(1)
        await BatchStatisticsCache(client, 300).invalidate(1)
        self.assertNotEqual(old, await cache.batch_key(1))
        client.get.side_effect = RedisError("offline")
        self.assertIsNone(await cache.get(first))
        self.assertIsNone(await cache.dashboard_key(**params))


class ApiTests(TestCase):
    def test_validation_does_not_call_services(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        dash = SimpleNamespace(get_dashboard=AsyncMock())
        comparison = SimpleNamespace(compare=AsyncMock())
        app.dependency_overrides[get_analytics_dashboard_service] = lambda: dash
        app.dependency_overrides[get_batch_comparison_service] = lambda: comparison
        with TestClient(app) as client:
            for payload in [
                {"batch_ids": [1, 1]},
                {"batch_ids": [1]},
                {"batch_ids": [1, 3000000000]},
            ]:
                self.assertEqual(
                    client.post(
                        "/api/v1/analytics/compare-batches", json=payload
                    ).status_code,
                    422,
                )
            self.assertEqual(
                client.get(
                    "/api/v1/analytics/dashboard?date_from=2026-10-04&date_to=2026-10-03"
                ).status_code,
                422,
            )
        comparison.compare.assert_not_awaited()
        dash.get_dashboard.assert_not_awaited()

    def test_successful_dto_responses_are_serialized_by_all_three_endpoints(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.include_router(batches_router, prefix="/api/v1")
        zero = {
            "total_batches": 0,
            "open_batches": 0,
            "closed_batches": 0,
            "total_products": 0,
            "aggregated_products": 0,
            "pending_products": 0,
            "aggregation_percent": 0,
        }
        dashboard = DashboardAnalytics(
            summary=zero, today=zero, by_shift=[], top_work_centers=[]
        )
        dash = SimpleNamespace(get_dashboard=AsyncMock(return_value=dashboard))
        comparison = SimpleNamespace(
            compare=AsyncMock(return_value=compare_batches([snapshot(1), snapshot(2)]))
        )
        batch = SimpleNamespace(
            get_statistics=AsyncMock(return_value=batch_analytics(snapshot(), NOW))
        )
        app.dependency_overrides[get_analytics_dashboard_service] = lambda: dash
        app.dependency_overrides[get_batch_comparison_service] = lambda: comparison
        app.dependency_overrides[get_batch_analytics_service] = lambda: batch
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/v1/analytics/dashboard").status_code, 200)
            response = client.post(
                "/api/v1/analytics/compare-batches", json={"batch_ids": [1, 2]}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["average"]["total_products"], 1000)
            response = client.get("/api/v1/batches/1/statistics")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["timeline"]["forecast_status"], "available"
            )
