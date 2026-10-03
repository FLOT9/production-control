from asyncio import to_thread

from sqlalchemy.exc import DataError, IntegrityError

from src.application.dto import (
    BatchImportProcessedRow,
    BatchImportResult,
    BatchImportRowError,
)
from src.application.importers.base import BatchParser
from src.application.services.batch_service import BatchService
from src.domain.exceptions.batch import BatchAlreadyExistsError
from src.domain.exceptions.work_center import WorkCenterNotFoundError


class BatchImportService:
    def __init__(
        self,
        parser: BatchParser,
        batch_service: BatchService,
    ) -> None:
        self.parser = parser
        self.batch_service = batch_service

    async def import_csv(
        self,
        data: bytes,
    ) -> BatchImportResult:
        return await self.import_file(data)

    async def import_file(self, data: bytes) -> BatchImportResult:
        parse_result = await to_thread(self.parser.parse, data)

        processed = []
        failed = list(parse_result.errors)

        for parsed_row in parse_result.valid_rows:
            try:
                batch = await self.batch_service.create(**parsed_row.data.model_dump())
            except (
                BatchAlreadyExistsError,
                WorkCenterNotFoundError,
            ) as error:
                await self.batch_service.uow.rollback()
                failed.append(
                    BatchImportRowError(
                        row_number=parsed_row.row_number,
                        reason=str(error),
                    )
                )
            except (DataError, IntegrityError):
                await self.batch_service.uow.rollback()
                failed.append(
                    BatchImportRowError(
                        row_number=parsed_row.row_number,
                        reason="Row violates database field or integrity constraints",
                    )
                )
            else:
                processed.append(
                    BatchImportProcessedRow(
                        row_number=parsed_row.row_number,
                        batch_id=batch.id,
                    )
                )

        return BatchImportResult(
            processed=processed,
            failed=failed,
        )
