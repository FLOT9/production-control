import asyncio

from celery import Task
from redis.asyncio import Redis

from src.application.services.product_service import (
    ProductAggregationResult,
    ProductService,
    ProgressCallback,
)
from src.application.services.webhook_event_service import WebhookEventService
from src.core.config import settings
from src.core.database import async_session_maker, dispose_engine
from src.data.unit_of_work import UnitOfWork
from src.storage.batch_details_cache import BatchDetailsCache
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache
from src.tasks.celery_app import celery_app


async def _aggregate_products(
    batch_id: int, unique_codes: list[str], on_progress: ProgressCallback
) -> ProductAggregationResult:
    client = Redis.from_url(
        settings.redis_cache_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        async with async_session_maker() as session:
            uow = UnitOfWork(session)
            service = ProductService(
                uow,
                BatchStatisticsCache(
                    client,
                    settings.batch_statistics_cache_ttl_seconds,
                ),
                DashboardCache(client, settings.dashboard_cache_ttl_seconds),
                WebhookEventService(uow),
                BatchDetailsCache(client, settings.batch_details_cache_ttl_seconds),
            )

            return await service.aggregate_many(
                batch_id=batch_id,
                unique_codes=unique_codes,
                on_progress=on_progress,
            )
    finally:
        try:
            await client.aclose()
        finally:
            await dispose_engine()


@celery_app.task(bind=True, name="products.aggregate_batch")
def aggregate_products(
    self: Task, batch_id: int, unique_codes: list[str]
) -> ProductAggregationResult:
    task_id = self.request.id

    async def report_progress(current: int, total: int) -> None:
        await asyncio.to_thread(
            self.update_state,
            task_id=task_id,
            state="PROGRESS",
            meta={
                "current": current,
                "total": total,
                "progress": current * 100 // total,
            },
        )

    return asyncio.run(_aggregate_products(batch_id, unique_codes, report_progress))
