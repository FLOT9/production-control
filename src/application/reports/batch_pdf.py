from collections import Counter
from datetime import UTC, timedelta
from html import escape
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.dates import DateFormatter, date2num
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.application.dto.batch_report import BatchReportData


class BatchPdfGenerator:
    def __init__(self, timezone: str) -> None:
        self.timezone = ZoneInfo(timezone)
        font_path = Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"
        if "BatchReportFont" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("BatchReportFont", str(font_path)))

    def generate(self, report: BatchReportData) -> bytes:
        output = BytesIO()
        style = ParagraphStyle(
            "body", fontName="BatchReportFont", fontSize=10, leading=15
        )
        title = ParagraphStyle(
            "title", parent=style, fontSize=18, leading=24, spaceAfter=15
        )
        batch = report.batch
        content: list[Flowable] = [
            Paragraph(f"Отчёт по партии №{batch.batch_number}", title)
        ]
        rows = [
            ("Дата партии", str(batch.batch_date)),
            ("Задание", batch.task_description),
            ("Рабочий центр", str(batch.work_center_id)),
            ("Смена", batch.shift),
            ("Бригада", batch.team),
            ("Номенклатура", batch.nomenclature),
            ("Код ЕКН", batch.ekn_code),
            (
                "Начало смены",
                batch.shift_start.astimezone(self.timezone).isoformat(
                    sep=" ", timespec="minutes"
                ),
            ),
            (
                "Окончание смены",
                batch.shift_end.astimezone(self.timezone).isoformat(
                    sep=" ", timespec="minutes"
                ),
            ),
            ("Статус", "Закрыта" if batch.is_closed else "Открыта"),
            ("Всего продуктов", str(report.statistics.total_products)),
            ("Агрегировано", str(report.statistics.aggregated_products)),
            ("Осталось", str(report.statistics.pending_products)),
            ("Процент агрегации", f"{report.statistics.aggregation_percent:.2f}%"),
        ]
        table = Table(
            [
                [Paragraph(escape(label), style), Paragraph(escape(value), style)]
                for label, value in rows
            ],
            colWidths=[5 * cm, 12 * cm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EDF2F7")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        content.extend(
            [
                table,
                Spacer(1, 0.5 * cm),
                Paragraph("Агрегация по времени — накопительное количество", style),
            ]
        )
        times = sorted(
            product.aggregated_at.astimezone(UTC)
            for product in report.products
            if product.is_aggregated and product.aggregated_at is not None
        )
        if times:
            counts = Counter(times)
            timestamps = sorted(counts)
            running = 0
            totals = []
            for timestamp in timestamps:
                running += counts[timestamp]
                totals.append(running)
            figure = Figure(figsize=(8, 3), constrained_layout=True)
            FigureCanvasAgg(figure)
            axes = figure.subplots()
            axes.step(
                date2num(timestamps), totals, where="post", color="#244062", marker="o"
            )
            axes.set_ylim(0, max(totals) + 1)
            axes.yaxis.set_major_locator(MaxNLocator(integer=True))
            if len(timestamps) == 1:
                axes.set_xlim(
                    date2num(timestamps[0] - timedelta(minutes=30)),
                    date2num(timestamps[0] + timedelta(minutes=30)),
                )
            axes.set_ylabel("Агрегировано, шт.")
            axes.set_xlabel(f"Время ({self.timezone.key})")
            axes.xaxis.set_major_formatter(
                DateFormatter("%d.%m %H:%M", tz=self.timezone)
            )
            axes.grid(alpha=0.2)
            figure.autofmt_xdate()
            chart = BytesIO()
            figure.savefig(chart, format="png", dpi=140)
            chart.seek(0)
            content.append(Image(chart, width=17 * cm, height=6.4 * cm))
        else:
            content.append(
                Paragraph(
                    "Агрегаций пока нет." if report.products else "Продукции пока нет.",
                    style,
                )
            )
        content.append(
            Paragraph(
                escape(
                    "Сформирован: "
                    + report.generated_at.astimezone(self.timezone).isoformat(
                        sep=" ", timespec="seconds"
                    )
                ),
                style,
            )
        )
        SimpleDocTemplate(output, topMargin=1.5 * cm, bottomMargin=1.5 * cm).build(
            content
        )
        return output.getvalue()
