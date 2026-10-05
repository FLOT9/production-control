from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StoredReport:
    report_id: UUID
    bucket: str
    object_name: str
