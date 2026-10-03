from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ProductionSummaryRow:
    work_center_identifier: str
    work_center_name: str
    batch_number: int
    batch_date: date
    shift: str
    team: str
    nomenclature: str
    ekn_code: str
    is_closed: bool
    products_total: int
    products_aggregated: int
