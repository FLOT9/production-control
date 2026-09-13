import asyncio

from src.application.reports.production_summary_excel import (
    ProductionSummaryExcelGenerator,
)
from src.application.services.production_summary_service import (
    ProductionSummaryService,
)
from src.core.database import async_session_maker, dispose_engine
from src.data.unit_of_work import UnitOfWork
from src.storage.object_storage import create_object_storage
from src.tasks.celery_app import celery_app


async def _generate_production_summary() -> dict[str, str]:
    try:
        async with async_session_maker() as session:
            uow = UnitOfWork(session)
            excel_generator = ProductionSummaryExcelGenerator()
            object_storage = create_object_storage()

            service = ProductionSummaryService(
                uow=uow,
                excel_generator=excel_generator,
                object_storage=object_storage,
            )

            report = await service.generate_and_upload()

            return {
                "report_id": str(report.report_id),
                "bucket": report.bucket,
                "object_name": report.object_name,
            }
    finally:
        await dispose_engine()


@celery_app.task(name="reports.generate_production_summary")
def generate_production_summary() -> dict[str, str]:
    return asyncio.run(_generate_production_summary())
