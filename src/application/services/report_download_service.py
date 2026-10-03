from asyncio import to_thread
from typing import Literal
from uuid import UUID

from minio.error import S3Error
from urllib3.exceptions import HTTPError

from src.application.dto.report_format import ReportFormat, report_extension
from src.application.exceptions import (
    ObjectStorageUnavailableError,
    ReportNotFoundError,
)
from src.storage.object_storage import ObjectStorage

REPORTS_BUCKET = "reports"


class ReportDownloadService:
    def __init__(self, object_storage: ObjectStorage) -> None:
        self.object_storage = object_storage

    async def get_production_summary_url(self, report_id: UUID) -> str:
        return await self._get_download_url(
            report_id,
            f"production-summary/{report_id}.xlsx",
        )

    async def get_batch_export_url(
        self, report_id: UUID, format: Literal["csv", "excel"] = "csv"
    ) -> str:
        object_name = (
            f"batch-exports/{report_id}.{'csv' if format == 'csv' else 'xlsx'}"
        )
        try:
            return await self._get_download_url(
                report_id, object_name, bucket="exports"
            )
        except ReportNotFoundError:
            if format != "csv":
                raise
            # CSV exports generated before the bucket correction remain downloadable.
            return await self._get_download_url(
                report_id, object_name, bucket="reports"
            )

    async def get_batch_report_url(
        self, batch_id: int, report_id: UUID, format: ReportFormat
    ) -> str:
        return await self._get_download_url(
            report_id, f"batches/{batch_id}/{report_id}.{report_extension(format)}"
        )

    async def _get_download_url(
        self, report_id: UUID, object_name: str, bucket: str = REPORTS_BUCKET
    ) -> str:

        try:
            await to_thread(
                self.object_storage.check_exists,
                bucket,
                object_name,
            )
            return await to_thread(
                self.object_storage.download_url,
                bucket,
                object_name,
            )
        except S3Error as error:
            if error.code == "NoSuchKey":
                raise ReportNotFoundError(report_id) from error

            raise ObjectStorageUnavailableError() from error
        except HTTPError as error:
            raise ObjectStorageUnavailableError() from error
