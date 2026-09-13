import csv
from collections.abc import Sequence
from io import StringIO

from src.data.models import Batch

HEADERS = (
    "id",
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
    "is_closed",
    "closed_at",
    "created_at",
    "updated_at",
)
FORMULA_PREFIXES = ("=", "+", "-", "@")


def _safe_text(value: str) -> str:
    if value.lstrip().startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


class BatchCsvExporter:
    def generate(self, batches: Sequence[Batch]) -> bytes:
        buffer = StringIO(newline="")
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow(HEADERS)

        for batch in batches:
            writer.writerow(
                (
                    batch.id,
                    _safe_text(batch.task_description),
                    batch.work_center_id,
                    _safe_text(batch.shift),
                    _safe_text(batch.team),
                    batch.batch_number,
                    batch.batch_date.isoformat(),
                    _safe_text(batch.nomenclature),
                    _safe_text(batch.ekn_code),
                    batch.shift_start.isoformat(),
                    batch.shift_end.isoformat(),
                    str(batch.is_closed).lower(),
                    batch.closed_at.isoformat() if batch.closed_at else "",
                    batch.created_at.isoformat(),
                    batch.updated_at.isoformat(),
                )
            )

        return buffer.getvalue().encode("utf-8-sig")
