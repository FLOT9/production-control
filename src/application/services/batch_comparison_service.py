from datetime import UTC, datetime

from src.application.analytics.calculator import compare_batches
from src.application.dto.analytics import BatchComparison
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import BatchComparisonInvalidError, BatchNotFoundError


class BatchComparisonService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def compare(self, batch_ids: list[int]) -> BatchComparison:
        if not 2 <= len(batch_ids) <= 10 or len(set(batch_ids)) != len(batch_ids):
            raise BatchComparisonInvalidError(
                "Provide between 2 and 10 unique batch IDs"
            )
        if any(not 0 < batch_id <= 2**31 - 1 for batch_id in batch_ids):
            raise BatchComparisonInvalidError("Batch IDs must be positive int32 values")
        rows = await self.uow.analytics.batch_snapshots(
            batch_ids, now=datetime.now(UTC)
        )
        by_id = {row.batch_info.id: row for row in rows}
        for batch_id in batch_ids:
            if batch_id not in by_id:
                raise BatchNotFoundError(batch_id)
        return compare_batches([by_id[batch_id] for batch_id in batch_ids])
