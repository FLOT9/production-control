from collections.abc import Sequence
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from src.application.reports.batch_csv import HEADERS
from src.data.models import Batch


class BatchExcelExporter:
    def generate(self, batches: Sequence[Batch]) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        if sheet is None:
            raise RuntimeError("Workbook has no worksheet")
        sheet.title = "Партии"
        sheet.append(list(HEADERS))
        for batch in batches:
            values = []
            for header in HEADERS:
                value = getattr(batch, header)
                if hasattr(value, "isoformat"):
                    value = value.isoformat()
                values.append(value)
            sheet.append(values)
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for index, cell in enumerate(sheet[1], start=1):
            sheet.column_dimensions[get_column_letter(index)].width = min(
                len(str(cell.value)) + 8, 40
            )
        data = BytesIO()
        workbook.save(data)
        workbook.close()
        return data.getvalue()
