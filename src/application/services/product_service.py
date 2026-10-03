import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy.exc import IntegrityError

from src.application.events import WebhookEvent, WebhookEventType
from src.application.services.webhook_event_service import WebhookEventService
from src.data.models import Product
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import BatchClosedError, BatchNotFoundError
from src.domain.exceptions.product import (
    ProductAlreadyAggregatedError,
    ProductAlreadyExistsError,
    ProductBatchMismatchError,
    ProductNotFoundError,
)
from src.storage.batch_details_cache import BatchDetailsCache
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache

logger = logging.getLogger(__name__)


class ProductAggregationError(TypedDict):
    unique_code: str
    reason: str


class ProductAggregationResult(TypedDict):
    success: bool
    total: int
    aggregated: int
    failed: int
    errors: list[ProductAggregationError]


ProgressCallback = Callable[[int, int], Awaitable[None]]


class ProductService:
    def __init__(
        self,
        uow: UnitOfWork,
        statistics_cache: BatchStatisticsCache,
        dashboard_cache: DashboardCache,
        webhook_event_service: WebhookEventService,
        details_cache: BatchDetailsCache,
    ) -> None:
        self.uow = uow
        self.statistics_cache = statistics_cache
        self.dashboard_cache = dashboard_cache
        self.webhook_event_service = webhook_event_service
        self.details_cache = details_cache

    async def create(
        self,
        *,
        unique_code: str,
        batch_id: int,
    ) -> Product:
        batch = await self.uow.batches.get_by_id_for_update(batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)

        if batch.is_closed:
            raise BatchClosedError(batch_id)

        product = await self.uow.products.get_by_unique_code(unique_code=unique_code)

        if product is not None:
            raise ProductAlreadyExistsError(product.unique_code)

        try:
            saved_product = await self.uow.products.create(
                unique_code=unique_code,
                batch_id=batch_id,
            )
        except IntegrityError as error:
            await self.uow.rollback()
            raise ProductAlreadyExistsError(unique_code) from error

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
        await self.statistics_cache.invalidate(batch_id)
        await self.details_cache.invalidate(batch_id)
        return saved_product

    async def aggregate_many(
        self,
        *,
        batch_id: int,
        unique_codes: list[str],
        on_progress: ProgressCallback | None = None,
    ) -> ProductAggregationResult:
        processed: list[str] = []
        failed: list[ProductAggregationError] = []

        for current, unique_code in enumerate(unique_codes, start=1):
            try:
                await self.aggregate(unique_code=unique_code, batch_id=batch_id)
            except (
                ProductNotFoundError,
                ProductBatchMismatchError,
                ProductAlreadyAggregatedError,
                BatchNotFoundError,
                BatchClosedError,
            ) as error:
                await self.uow.rollback()
                failed.append({"unique_code": unique_code, "reason": str(error)})
            else:
                processed.append(unique_code)

            if on_progress is not None:
                try:
                    await on_progress(current, len(unique_codes))
                except Exception:
                    # Progress is advisory; each product already has its own outcome.
                    logger.warning(
                        "Cannot publish aggregation progress for batch %s (%s/%s)",
                        batch_id,
                        current,
                        len(unique_codes),
                        exc_info=True,
                    )

        return {
            "success": len(failed) == 0,
            "total": len(unique_codes),
            "aggregated": len(processed),
            "failed": len(failed),
            "errors": failed,
        }

    async def aggregate(
        self,
        *,
        unique_code: str,
        batch_id: int,
    ) -> Product:
        product = await self.uow.products.get_by_unique_code_for_update(
            unique_code=unique_code
        )
        if product is None:
            raise ProductNotFoundError(unique_code)
        if batch_id != product.batch_id:
            raise ProductBatchMismatchError(
                unique_code,
                expected_batch_id=batch_id,
                actual_batch_id=product.batch_id,
            )
        batch = await self.uow.batches.get_by_id_for_update(product.batch_id)
        if batch is None:
            raise BatchNotFoundError(product.batch_id)
        if batch.is_closed:
            raise BatchClosedError(product.batch_id)
        if product.is_aggregated:
            raise ProductAlreadyAggregatedError(unique_code)

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
        await self.statistics_cache.invalidate(product.batch_id)
        await self.details_cache.invalidate(product.batch_id)
        return product
