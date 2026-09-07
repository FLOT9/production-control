import asyncio

from src.core.database import async_session_maker, dispose_engine
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import BatchClosedError
from src.domain.exceptions.product import ProductNotFoundError
from src.domain.services.product_service import ProductService
from src.tasks.celery_app import celery_app


async def _aggregate_products(unique_codes: list[str]) -> dict:
    try:
        async with async_session_maker() as session:
            uow = UnitOfWork(session)
            service = ProductService(uow)

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
        await dispose_engine()


@celery_app.task(name="products.aggregate_many")
def aggregate_products(unique_codes: list[str]) -> dict:
    return asyncio.run(_aggregate_products(unique_codes))
