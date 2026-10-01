import asyncio
import json
import unittest
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from src.application.services.batch_service import BatchService
from src.storage.batch_details_cache import BatchDetailsCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True


def batch(*, is_closed: bool) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        products=[],
        id=42,
        task_description="Example",
        work_center_id=1,
        shift="day",
        team="A",
        batch_number=7,
        batch_date=date(2026, 9, 28),
        nomenclature="Part",
        ekn_code="EKN",
        shift_start=now,
        shift_end=now + timedelta(hours=8),
        is_closed=is_closed,
        closed_at=now if is_closed else None,
        created_at=now,
        updated_at=now,
    )


class BatchDetailsCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_read_cannot_repopulate_current_generation(self) -> None:
        redis = FakeRedis()
        cache = BatchDetailsCache(redis, ttl_seconds=600)
        first_read_started = asyncio.Event()
        resume_first_read = asyncio.Event()
        database_value = batch(is_closed=False)
        reads = 0

        async def get_with_products(batch_id: int) -> SimpleNamespace:
            nonlocal database_value, reads
            reads += 1
            row = database_value
            if reads == 1:
                first_read_started.set()
                await resume_first_read.wait()
            return row

        service = BatchService(
            uow=SimpleNamespace(
                batches=SimpleNamespace(get_with_products=get_with_products)
            ),
            statistics_cache=None,
            dashboard_cache=None,
            list_cache=None,
            details_cache=cache,
            webhook_event_service=None,
        )

        old_read = asyncio.create_task(service.get_by_id(42))
        await first_read_started.wait()
        old_key = await cache.make_key(42)

        database_value = batch(is_closed=True)
        await cache.invalidate(42)
        resume_first_read.set()
        await old_read

        new_key = await cache.make_key(42)
        self.assertNotEqual(old_key, new_key)
        self.assertFalse(json.loads(redis.values[old_key])["is_closed"])

        current = await service.get_by_id(42)
        self.assertTrue(current.is_closed)
        self.assertEqual(reads, 2)
        self.assertTrue(json.loads(redis.values[new_key])["is_closed"])
