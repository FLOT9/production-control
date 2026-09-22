import asyncio

from redis.asyncio import Redis

from src.application.services.product_service import ProductService
from src.application.services.webhook_event_service import WebhookEventService
from src.core.config import settings
from src.core.database import async_session_maker, dispose_engine
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import BatchClosedError
from src.domain.exceptions.product import ProductNotFoundError
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache
from src.tasks.celery_app import celery_app


async def _aggregate_products(unique_codes: list[str]) -> dict:
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
            )

            processed: list[str] = []
            failed: list[dict[str, str]] = []

            for product_code in unique_codes:
                try:
                    await service.aggregate(unique_code=product_code)
                except (ProductNotFoundError, BatchClosedError) as exc:
                    failed.append(
                        {
                            "unique_code": product_code,
                            "reason": str(exc),
                        }
                    )
                else:
                    processed.append(product_code)

            return {
                "processed": processed,
                "failed": failed,
            }
    finally:
        try:
            await client.aclose()
        finally:
            await dispose_engine()


@celery_app.task(name="products.aggregate_many")
def aggregate_products(unique_codes: list[str]) -> dict:
    return asyncio.run(_aggregate_products(unique_codes))
