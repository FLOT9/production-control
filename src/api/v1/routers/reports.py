from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from starlette import status
from starlette.concurrency import run_in_threadpool

from src.api.v1.schemas import (
    ReportGenerationTaskRead,
    ReportGenerationTaskStatusRead,
)
from src.application.services.report_download_service import ReportDownloadService
from src.core.dependencies import get_report_download_service
from src.tasks.report_tasks import (
    generate_production_summary as generate_production_summary_task,
)
from src.tasks.task_status import get_task_status

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
)


@router.post(
    "/production-summary",
    response_model=ReportGenerationTaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_production_summary() -> ReportGenerationTaskRead:
    task = await run_in_threadpool(
        generate_production_summary_task.delay,
    )

    return ReportGenerationTaskRead(task_id=task.id)


@router.get(
    "/tasks/{task_id}",
    response_model=ReportGenerationTaskStatusRead,
)
async def report_task_status(task_id: str) -> ReportGenerationTaskStatusRead:
    task_data = await run_in_threadpool(get_task_status, task_id)
    return ReportGenerationTaskStatusRead(**task_data)


@router.get("/{report_id}/download")
async def download_report(
    report_id: UUID,
    service: Annotated[
        ReportDownloadService,
        Depends(get_report_download_service),
    ],
) -> RedirectResponse:
    url = await service.get_production_summary_url(report_id)
    return RedirectResponse(
        url=url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
