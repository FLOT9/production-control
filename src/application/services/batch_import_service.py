from src.application.dto import (
    BatchImportProcessedRow,
    BatchImportResult,
    BatchImportRowError,
)
from src.application.importers import BatchCsvParser
from src.application.services.batch_service import BatchService
from src.domain.exceptions.batch import BatchAlreadyExistsError
from src.domain.exceptions.work_center import WorkCenterNotFoundError


class BatchImportService:
    def __init__(
        self,
        parser: BatchCsvParser,
        batch_service: BatchService,
    ) -> None:
        self.parser = parser
        self.batch_service = batch_service

    async def import_csv(
        self,
        data: bytes,
    ) -> BatchImportResult:
        parse_result = self.parser.parse(data)

        processed = []
        failed = list(parse_result.errors)

        for parsed_row in parse_result.valid_rows:
            try:
                batch = await self.batch_service.create(**parsed_row.data.model_dump())
            except (
                BatchAlreadyExistsError,
                WorkCenterNotFoundError,
            ) as error:
                failed.append(
                    BatchImportRowError(
                        row_number=parsed_row.row_number,
                        reason=str(error),
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
