from datetime import UTC, date, datetime
from typing import cast

from sqlalchemy.exc import IntegrityError

from src.application.dto import (
    BatchFilters,
    BatchIntegrationData,
    BatchProductCounts,
    BatchStatistics,
)
from src.application.events import WebhookEvent, WebhookEventType
from src.application.services.webhook_event_service import WebhookEventService
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
        webhook_event_service: WebhookEventService,
    ) -> None:
        self.uow = uow
        self.statistics_cache = statistics_cache
        self.dashboard_cache = dashboard_cache
        self.list_cache = list_cache
        self.details_cache = details_cache
        self.webhook_event_service = webhook_event_service

    async def get_by_id(self, batch_id: int) -> Batch | dict[str, object]:
        key = await self.details_cache.make_key(batch_id)
        cached = await self.details_cache.get(key, batch_id)
        if cached is not None:
            return cached
        batch = await self._get_from_db(batch_id)
        await self.details_cache.set(key, batch)
        return batch

    async def _get_from_db(self, batch_id: int) -> Batch:
        batch = await self.uow.batches.get_by_id(instance_id=batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)

        return batch

    async def _get_for_update(self, batch_id: int) -> Batch:
        batch = await self.uow.batches.get_by_id_for_update(batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)
        return batch

    async def _invalidate_batch_caches(self, batch_id: int) -> None:
        await self.dashboard_cache.invalidate()
        await self.list_cache.invalidate()
        await self.statistics_cache.invalidate(batch_id)
        await self.details_cache.invalidate(batch_id)

    async def get_statistics(self, batch_id: int) -> BatchStatistics:
        key = await self.statistics_cache.make_key(batch_id)
        cached = await self.statistics_cache.get(key, batch_id)
        if cached is not None:
            return cached

        counts = await self.uow.batches.get_statistics(batch_id)
        if counts is None:
            raise BatchNotFoundError(batch_id)

        statistics = self._build_statistics(counts)
        await self.statistics_cache.set(key, statistics)
        return statistics

    async def compare_batches(self, batch_ids: list[int]) -> list[BatchStatistics]:
        if not 2 <= len(batch_ids) <= 10:
            raise BatchComparisonInvalidError("Provide between 2 and 10 batch IDs")
        if any(batch_id <= 0 for batch_id in batch_ids):
            raise BatchComparisonInvalidError("Batch IDs must be positive")
        if len(set(batch_ids)) != len(batch_ids):
            raise BatchComparisonInvalidError("Batch IDs must be unique")

        keys = await self.statistics_cache.make_keys(batch_ids)
        by_id = await self.statistics_cache.get_many(keys)
        missing_ids = [batch_id for batch_id in batch_ids if batch_id not in by_id]
        if missing_ids:
            rows = await self.uow.batches.get_statistics_many(missing_ids)
            loaded = {row.batch_id: self._build_statistics(row) for row in rows}
            for batch_id in missing_ids:
                if batch_id not in loaded:
                    raise BatchNotFoundError(batch_id)
            await self.statistics_cache.set_many(keys, list(loaded.values()))
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
        batch = await self._get_for_update(batch_id)
        return await self._update_locked(batch, changes)

    async def close_if_expired(self, batch_id: int, expired_before: datetime) -> bool:
        try:
            batch = await self._get_for_update(batch_id)
            if batch.is_closed or batch.shift_end >= expired_before:
                await self.uow.rollback()
                return False
            await self._update_locked(batch, {"is_closed": True})
        except BatchNotFoundError:
            await self.uow.rollback()
            return False
        except Exception:
            await self.uow.rollback()
            raise
        return True

    async def close_expired_batches(
        self, *, expired_before: datetime, page_size: int = 200
    ) -> dict[str, int]:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        result = {"checked": 0, "closed": 0, "skipped": 0}
        after_id = 0
        while True:
            ids = await self.uow.batches.list_expired_ids(
                expired_before=expired_before, after_id=after_id, limit=page_size
            )
            if not ids:
                return result
            for batch_id in ids:
                closed = await self.close_if_expired(batch_id, expired_before)
                result["checked"] += 1
                result["closed" if closed else "skipped"] += 1
            after_id = ids[-1]

    async def _update_locked(self, batch: Batch, changes: dict[str, object]) -> Batch:
        batch_id = batch.id

        if not changes:
            return batch

        was_closed = batch.is_closed

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

        event_type = WebhookEventType.BATCH_UPDATED
        if batch.is_closed != was_closed:
            event_type = (
                WebhookEventType.BATCH_CLOSED
                if batch.is_closed
                else WebhookEventType.BATCH_REOPENED
            )

        await self.webhook_event_service.create_deliveries(
            WebhookEvent(
                event_type=event_type,
                data={
                    "batch_id": batch.id,
                    "batch_number": batch.batch_number,
                    "batch_date": batch.batch_date.isoformat(),
                    "work_center_id": batch.work_center_id,
                    "shift": batch.shift,
                    "is_closed": batch.is_closed,
                    "changed_fields": sorted(changes),
                },
            )
        )

        await self.uow.commit()
        await self._invalidate_batch_caches(batch_id)
        await self.uow.batches.refresh(batch)
        return batch

    async def delete(self, batch_id: int) -> None:
        batch = await self._get_for_update(batch_id)

        has_products = await self.uow.products.exists_by_batch_id(batch_id)
        if has_products:
            raise BatchHasProductsError(batch_id)

        await self.uow.batches.delete(batch)
        await self.uow.commit()
        await self._invalidate_batch_caches(batch_id)

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
        try:
            saved_batch = await self._create_uncommitted(
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
        except Exception:
            await self.uow.rollback()
            raise

        await self.dashboard_cache.invalidate()
        await self.list_cache.invalidate()
        return saved_batch

    async def create_many(self, items: list[BatchIntegrationData]) -> list[Batch]:
        if not items:
            return []

        batches: list[Batch] = []
        work_center_ids: dict[str, int] = {}
        try:
            for item in items:
                identifier = item.work_center_identifier
                if identifier not in work_center_ids:
                    work_center = (
                        await self.uow.work_centers.get_or_create_by_identifier(
                            identifier=identifier,
                            name=item.work_center_name,
                        )
                    )
                    work_center_ids[identifier] = work_center.id

                batch = await self._create_uncommitted(
                    task_description=item.task_description,
                    work_center_id=work_center_ids[identifier],
                    shift=item.shift,
                    team=item.team,
                    batch_number=item.batch_number,
                    batch_date=item.batch_date,
                    nomenclature=item.nomenclature,
                    ekn_code=item.ekn_code,
                    shift_start=item.shift_start,
                    shift_end=item.shift_end,
                    is_closed=item.is_closed,
                )
                batches.append(batch)
            await self.uow.commit()
        except Exception:
            await self.uow.rollback()
            raise

        await self.dashboard_cache.invalidate()
        await self.list_cache.invalidate()
        return batches

    async def _create_uncommitted(
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
        is_closed: bool = False,
    ) -> Batch:
        if shift_end <= shift_start:
            raise BatchInvalidShiftPeriodError()

        work_center = await self.uow.work_centers.get_by_id(work_center_id)
        if work_center is None:
            raise WorkCenterNotFoundError(work_center_id)

        existing_batch = await self.uow.batches.get_by_number_and_date(
            batch_number,
            batch_date,
        )
        if existing_batch is not None:
            raise BatchAlreadyExistsError(batch_number, batch_date)

        try:
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
                is_closed=is_closed,
                closed_at=datetime.now(UTC) if is_closed else None,
            )
        except IntegrityError as error:
            raise BatchAlreadyExistsError(batch_number, batch_date) from error

        await self.webhook_event_service.create_deliveries(
            WebhookEvent(
                event_type=WebhookEventType.BATCH_CREATED,
                data={
                    "batch_id": saved_batch.id,
                    "batch_number": saved_batch.batch_number,
                    "batch_date": saved_batch.batch_date.isoformat(),
                    "work_center_id": saved_batch.work_center_id,
                    "shift": saved_batch.shift,
                    "is_closed": saved_batch.is_closed,
                },
            )
        )

        return saved_batch

    async def list_batches(
        self,
        *,
        filters: BatchFilters,
        offset: int,
        limit: int,
    ) -> tuple[list[Batch] | list[dict[str, object]], int]:
        key = await self.list_cache.make_key(
            filters=filters, offset=offset, limit=limit
        )
        cached = await self.list_cache.get(key)
        if cached is not None:
            return cached
        batches = await self.uow.batches.find_by_filters(
            filters=filters, offset=offset, limit=limit
        )
        total = await self.uow.batches.count_by_filters(filters=filters)

        await self.list_cache.set(key, batches, total)
        return batches, total
