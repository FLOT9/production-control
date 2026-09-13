from datetime import UTC, date, datetime
from typing import cast

from src.data.models import Batch
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import (
    BatchAlreadyExistsError,
    BatchHasProductsError,
    BatchInvalidShiftPeriodError,
    BatchNotFoundError,
)
from src.domain.exceptions.work_center import WorkCenterNotFoundError

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
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def get_by_id(self, batch_id: int) -> Batch:
        batch = await self.uow.batches.get_by_id(instance_id=batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)

        return batch

    async def update(
        self,
        batch_id: int,
        changes: dict[str, object],
    ) -> Batch:
        batch = await self.get_by_id(batch_id)

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
        await self.uow.batches.refresh(batch)
        return batch

    async def delete(self, batch_id: int) -> None:
        batch = await self.get_by_id(batch_id)

        has_products = await self.uow.products.exists_by_batch_id(batch_id)
        if has_products:
            raise BatchHasProductsError(batch_id)

        await self.uow.batches.delete(batch)
        await self.uow.commit()

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
    ) -> tuple[list[Batch], int]:
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

        return batches, total
