from datetime import UTC, date, datetime
from typing import cast

from src.application.dto import BatchProductCounts, BatchStatistics
from src.data.models import Batch
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import (
    BatchAlreadyExistsError,
    BatchComparisonInvalidError,
    BatchHasProductsError,
    BatchInvalidShiftPeriodError,
    BatchNotFoundError,
)
from src.domain.exceptions.work_center import WorkCenterNotFoundError
from src.storage.batch_details_cache import BatchDetailsCache
from src.storage.batch_list_cache import BatchListCache
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache

UPDATABLE_BATCH_FIELDS = (
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
)


class BatchService:
    def __init__(
        self,
        uow: UnitOfWork,
        statistics_cache: BatchStatisticsCache,
        dashboard_cache: DashboardCache,
        list_cache: BatchListCache,
        details_cache: BatchDetailsCache,
    ) -> None:
        self.uow = uow
        self.statistics_cache = statistics_cache
        self.dashboard_cache = dashboard_cache
        self.list_cache = list_cache
        self.details_cache = details_cache

    async def get_by_id(self, batch_id: int) -> Batch | dict[str, object]:
        cached = await self.details_cache.get(batch_id)
        if cached is not None:
            return cached
        batch = await self._get_from_db(batch_id)
        await self.details_cache.set(batch)
        return batch

    async def _get_from_db(self, batch_id: int) -> Batch:
        batch = await self.uow.batches.get_by_id(instance_id=batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)

        return batch

    async def get_statistics(self, batch_id: int) -> BatchStatistics:
        cached = await self.statistics_cache.get(batch_id)
        if cached is not None:
            return cached

        counts = await self.uow.batches.get_statistics(batch_id)
        if counts is None:
            raise BatchNotFoundError(batch_id)

        statistics = self._build_statistics(counts)
        await self.statistics_cache.set(statistics)
        return statistics

    async def compare_batches(self, batch_ids: list[int]) -> list[BatchStatistics]:
        if not 2 <= len(batch_ids) <= 10:
            raise BatchComparisonInvalidError("Provide between 2 and 10 batch IDs")
        if any(batch_id <= 0 for batch_id in batch_ids):
            raise BatchComparisonInvalidError("Batch IDs must be positive")
        if len(set(batch_ids)) != len(batch_ids):
            raise BatchComparisonInvalidError("Batch IDs must be unique")

        by_id = await self.statistics_cache.get_many(batch_ids)
        missing_ids = [batch_id for batch_id in batch_ids if batch_id not in by_id]
        if missing_ids:
            rows = await self.uow.batches.get_statistics_many(missing_ids)
            loaded = {row.batch_id: self._build_statistics(row) for row in rows}
            for batch_id in missing_ids:
                if batch_id not in loaded:
                    raise BatchNotFoundError(batch_id)
            await self.statistics_cache.set_many(list(loaded.values()))
            by_id.update(loaded)
        return [by_id[batch_id] for batch_id in batch_ids]

    @staticmethod
    def _build_statistics(counts: BatchProductCounts) -> BatchStatistics:
        pending_products = counts.total_products - counts.aggregated_products
        aggregation_percent = (
            counts.aggregated_products / counts.total_products * 100
            if counts.total_products
            else 0.0
        )

        return BatchStatistics(
            batch_id=counts.batch_id,
            total_products=counts.total_products,
            aggregated_products=counts.aggregated_products,
            pending_products=pending_products,
            aggregation_percent=round(aggregation_percent, 2),
        )

    async def update(
        self,
        batch_id: int,
        changes: dict[str, object],
    ) -> Batch:
        batch = await self._get_from_db(batch_id)

        if not changes:
            return batch

        work_center_id = cast(
            int,
            changes.get("work_center_id", batch.work_center_id),
        )
        if work_center_id != batch.work_center_id:
            work_center = await self.uow.work_centers.get_by_id(work_center_id)
            if work_center is None:
                raise WorkCenterNotFoundError(work_center_id)

        batch_number = cast(int, changes.get("batch_number", batch.batch_number))
        batch_date = cast(date, changes.get("batch_date", batch.batch_date))
        if batch_number != batch.batch_number or batch_date != batch.batch_date:
            existing_batch = await self.uow.batches.get_by_number_and_date(
                batch_number,
                batch_date,
            )
            if existing_batch is not None and existing_batch.id != batch.id:
                raise BatchAlreadyExistsError(batch_number, batch_date)

        shift_start = cast(datetime, changes.get("shift_start", batch.shift_start))
        shift_end = cast(datetime, changes.get("shift_end", batch.shift_end))
        if shift_end <= shift_start:
            raise BatchInvalidShiftPeriodError()

        for field_name in UPDATABLE_BATCH_FIELDS:
            if field_name in changes:
                setattr(batch, field_name, changes[field_name])

        if "is_closed" in changes:
            is_closed = cast(bool, changes["is_closed"])
            if batch.is_closed != is_closed:
                batch.is_closed = is_closed
                batch.closed_at = datetime.now(UTC) if is_closed else None

        await self.uow.commit()
        await self.dashboard_cache.invalidate()
        await self.list_cache.invalidate()
        await self.statistics_cache.delete(batch_id)
        await self.details_cache.delete(batch_id)
        await self.uow.batches.refresh(batch)
        return batch

    async def delete(self, batch_id: int) -> None:
        batch = await self._get_from_db(batch_id)

        has_products = await self.uow.products.exists_by_batch_id(batch_id)
        if has_products:
            raise BatchHasProductsError(batch_id)

        await self.uow.batches.delete(batch)
        await self.uow.commit()
        await self.dashboard_cache.invalidate()
        await self.list_cache.invalidate()
        await self.statistics_cache.delete(batch_id)
        await self.details_cache.delete(batch_id)

    async def create(
        self,
        *,
        task_description: str,
        work_center_id: int,
        shift: str,
        team: str,
        batch_number: int,
        batch_date: date,
        nomenclature: str,
        ekn_code: str,
        shift_start: datetime,
        shift_end: datetime,
    ) -> Batch:
        work_center = await self.uow.work_centers.get_by_id(work_center_id)
        if work_center is None:
            raise WorkCenterNotFoundError(work_center_id)

        existing_batch = await self.uow.batches.get_by_number_and_date(
            batch_number,
            batch_date,
        )
        if existing_batch is not None:
            raise BatchAlreadyExistsError(batch_number, batch_date)

        saved_batch = await self.uow.batches.create(
            task_description=task_description,
            work_center_id=work_center_id,
            shift=shift,
            team=team,
            batch_number=batch_number,
            batch_date=batch_date,
            nomenclature=nomenclature,
            ekn_code=ekn_code,
            shift_start=shift_start,
            shift_end=shift_end,
        )

        await self.uow.commit()
        await self.dashboard_cache.invalidate()
        await self.list_cache.invalidate()
        return saved_batch

    async def list_batches(
        self,
        *,
        is_closed: bool | None,
        offset: int,
        limit: int,
        batch_number: int | None,
        batch_date: date | None,
        work_center_id: int | None,
        shift: str | None,
    ) -> tuple[list[Batch] | list[dict[str, object]], int]:
        key = await self.list_cache.make_key(
            is_closed=is_closed,
            offset=offset,
            limit=limit,
            batch_number=batch_number,
            batch_date=batch_date,
            work_center_id=work_center_id,
            shift=shift,
        )
        cached = await self.list_cache.get(key)
        if cached is not None:
            return cached
        batches = await self.uow.batches.find_by_filters(
            is_closed=is_closed,
            offset=offset,
            limit=limit,
            batch_number=batch_number,
            batch_date=batch_date,
            work_center_id=work_center_id,
            shift=shift,
        )

        total = await self.uow.batches.count_by_filters(
            is_closed=is_closed,
            batch_number=batch_number,
            batch_date=batch_date,
            work_center_id=work_center_id,
            shift=shift,
        )

        await self.list_cache.set(key, batches, total)
        return batches, total
