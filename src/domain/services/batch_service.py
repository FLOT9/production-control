from datetime import UTC, date, datetime

from src.data.models import Batch
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import BatchAlreadyExistsError, BatchNotFoundError
from src.domain.exceptions.work_center import WorkCenterNotFoundError


class BatchService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def get_by_id(self, batch_id: int) -> Batch:
        batch = await self.uow.batches.get_by_id(instance_id=batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)

        return batch

    async def update_status(
        self,
        batch_id: int,
        is_closed: bool,
    ) -> Batch:
        batch = await self.get_by_id(batch_id)

        if batch.is_closed == is_closed:
            return batch

        batch.is_closed = is_closed
        batch.closed_at = datetime.now(UTC) if is_closed else None

        await self.uow.commit()
        await self.uow.batches.refresh(batch)
        return batch

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
