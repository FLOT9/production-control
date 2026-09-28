import csv
from io import StringIO

from pydantic import ValidationError

from src.application.dto import (
    BatchCsvParseResult,
    BatchImportRow,
    BatchImportRowError,
    ParsedBatchImportRow,
)
from src.application.exceptions import BatchCsvHeadersError

REQUIRED_HEADERS = {
    "task_description",
    "work_center_id",
    "shift",
    "team",
    "batch_number",
    "batch_date",
    "nomenclature",
    "ekn_code",
    "shift_start",
    "shift_end",
}


class BatchCsvParser:
    def read_rows(
        self,
        data: bytes,
    ) -> list[dict[str, str]]:
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(
            StringIO(text),
            delimiter=";",
        )
        headers = set(reader.fieldnames or ())
        missing_headers = REQUIRED_HEADERS - headers

        if missing_headers:
            raise BatchCsvHeadersError(sorted(missing_headers))

        return list(reader)

    def parse(self, data: bytes) -> BatchCsvParseResult:
        raw_rows = self.read_rows(data)
        valid_rows: list[ParsedBatchImportRow] = []
        errors: list[BatchImportRowError] = []

        for row_number, raw_row in enumerate(raw_rows, start=2):
            if None in raw_row:
                errors.append(
                    BatchImportRowError(
                        row_number=row_number,
                        reason="CSV row has more values than headers",
                    )
                )
                continue

            try:
                row = BatchImportRow.model_validate(raw_row)
            except ValidationError as error:
                errors.append(
                    BatchImportRowError(
                        row_number=row_number,
                        reason=str(error),
                    )
                )
            else:
                valid_rows.append(
                    ParsedBatchImportRow(
                        row_number=row_number,
                        data=row,
                    )
                )

        return BatchCsvParseResult(
            valid_rows=valid_rows,
            errors=errors,
        )
