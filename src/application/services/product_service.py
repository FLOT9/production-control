from datetime import UTC, datetime

from src.application.events import WebhookEvent, WebhookEventType
from src.application.services.webhook_event_service import WebhookEventService
from src.data.models import Product
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import BatchClosedError, BatchNotFoundError
from src.domain.exceptions.product import (
    ProductAlreadyExistsError,
    ProductNotFoundError,
)
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache


class ProductService:
    def __init__(
        self,
        uow: UnitOfWork,
        statistics_cache: BatchStatisticsCache,
        dashboard_cache: DashboardCache,
        webhook_event_service: WebhookEventService,
    ) -> None:
        self.uow = uow
        self.statistics_cache = statistics_cache
        self.dashboard_cache = dashboard_cache
        self.webhook_event_service = webhook_event_service

    async def create(
        self,
        *,
        unique_code: str,
        batch_id: int,
    ) -> Product:
        batch = await self.uow.batches.get_by_id(instance_id=batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)

        if batch.is_closed:
            raise BatchClosedError(batch_id)

        product = await self.uow.products.get_by_unique_code(unique_code=unique_code)

        if product is not None:
            raise ProductAlreadyExistsError(product.unique_code)

        saved_product = await self.uow.products.create(
            unique_code=unique_code,
            batch_id=batch_id,
        )

        await self.webhook_event_service.create_deliveries(
            WebhookEvent(
                event_type=WebhookEventType.PRODUCT_CREATED,
                data={
                    "product_id": saved_product.id,
                    "unique_code": saved_product.unique_code,
                    "batch_id": saved_product.batch_id,
                },
            )
        )

        await self.uow.commit()
        await self.dashboard_cache.invalidate()
        await self.statistics_cache.delete(batch_id)
        return saved_product

    async def aggregate(
        self,
        *,
        unique_code: str,
    ) -> Product:
        product = await self.uow.products.get_by_unique_code(unique_code=unique_code)
        if product is None:
            raise ProductNotFoundError(unique_code)
        batch = await self.uow.batches.get_by_id(instance_id=product.batch_id)
        if batch.is_closed:
            raise BatchClosedError(product.batch_id)
        if product.is_aggregated:
            return product

        product.is_aggregated = True
        product.aggregated_at = datetime.now(UTC)

        await self.webhook_event_service.create_deliveries(
            WebhookEvent(
                event_type=WebhookEventType.PRODUCT_AGGREGATED,
                data={
                    "product_id": product.id,
                    "unique_code": product.unique_code,
                    "batch_id": product.batch_id,
                    "aggregated_at": product.aggregated_at.isoformat(),
                },
            )
        )

        await self.uow.commit()
        await self.dashboard_cache.invalidate()
        await self.statistics_cache.delete(product.batch_id)
        return product
