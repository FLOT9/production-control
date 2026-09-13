from asyncio import to_thread
from uuid import UUID

from minio.error import S3Error
from urllib3.exceptions import HTTPError

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

    async def get_batch_export_url(self, report_id: UUID) -> str:
        return await self._get_download_url(
            report_id,
            f"batch-exports/{report_id}.csv",
        )

    async def _get_download_url(self, report_id: UUID, object_name: str) -> str:

        try:
            await to_thread(
                self.object_storage.check_exists,
                REPORTS_BUCKET,
                object_name,
            )
            return await to_thread(
                self.object_storage.download_url,
                REPORTS_BUCKET,
                object_name,
            )
        except S3Error as error:
            if error.code == "NoSuchKey":
                raise ReportNotFoundError(report_id) from error

            raise ObjectStorageUnavailableError() from error
        except HTTPError as error:
            raise ObjectStorageUnavailableError() from error
