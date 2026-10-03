from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from src.api.dependencies.batches import get_batch_service
from src.api.v1.routers.batches import router
from src.api.v1.schemas import BatchDetailsRead, BatchRead
from src.application.services.batch_service import BatchService
from src.application.services.product_service import ProductService
from src.core.database import Base
from src.data.models import Batch, Product, WorkCenter
from src.data.repositories.batch_repository import BatchRepository
from src.domain.exceptions.batch import BatchNotFoundError
from src.storage.batch_details_cache import BatchDetailsCache
from tests.unit.test_batch_details_cache import FakeRedis, batch


def product():
    return SimpleNamespace(
        id=15, batch_id=42, unique_code="P-001", is_aggregated=False, aggregated_at=None
    )


class BatchProductsTests(IsolatedAsyncioTestCase):
    async def test_details_cache_and_api_schema_preserve_products(self):
        row = batch(is_closed=False)
        row.products = [product()]
        cache = BatchDetailsCache(FakeRedis(), 600)
        repo = SimpleNamespace(get_with_products=AsyncMock(return_value=row))
        service = BatchService(
            SimpleNamespace(batches=repo), None, None, None, cache, None
        )
        first = BatchDetailsRead.model_validate(await service.get_by_id(42))
        cached = BatchDetailsRead.model_validate(await service.get_by_id(42))
        third = BatchDetailsRead.model_validate(await service.get_by_id(42))
        self.assertEqual(third, cached)
        self.assertEqual(first, cached)
        self.assertEqual(cached.products[0].unique_code, "P-001")
        self.assertEqual(repo.get_with_products.await_count, 2)
        self.assertNotIn("products", BatchRead.model_validate(row).model_dump())

    async def test_empty_products_and_missing_batch(self):
        cache = BatchDetailsCache(FakeRedis(), 600)
        repo = SimpleNamespace(
            get_with_products=AsyncMock(return_value=batch(is_closed=False))
        )
        service = BatchService(
            SimpleNamespace(batches=repo), None, None, None, cache, None
        )
        self.assertEqual(
            BatchDetailsRead.model_validate(await service.get_by_id(42)).products, []
        )
        repo.get_with_products.return_value = None
        with self.assertRaises(BatchNotFoundError):
            await service.get_by_id(999)

    async def test_old_cache_without_products_is_not_accepted(self):
        redis = FakeRedis()
        cache = BatchDetailsCache(redis, 600)
        key = await cache.make_key(42)
        self.assertIn(":v3:", key)
        redis.values[key] = BatchRead.model_validate(
            batch(is_closed=False)
        ).model_dump_json()
        self.assertIsNone(await cache.get(key, 42))

    async def test_product_changes_invalidate_only_after_successful_commit(self):
        for operation in ["create", "aggregate"]:
            for fail in [False, True]:
                with self.subTest(operation=operation, fail=fail):
                    row = product()
                    calls = []

                    async def commit(calls=calls, fail=fail):
                        calls.append("commit")
                        if fail:
                            raise RuntimeError("commit failed")

                    async def invalidate(batch_id, calls=calls):
                        calls.append(("invalidate", batch_id))

                    uow = SimpleNamespace(
                        commit=AsyncMock(side_effect=commit),
                        batches=SimpleNamespace(
                            get_by_id_for_update=AsyncMock(
                                return_value=batch(is_closed=False)
                            )
                        ),
                        products=SimpleNamespace(
                            get_by_unique_code=AsyncMock(return_value=None),
                            get_by_unique_code_for_update=AsyncMock(return_value=row),
                            create=AsyncMock(return_value=row),
                        ),
                    )
                    details = SimpleNamespace(
                        invalidate=AsyncMock(side_effect=invalidate)
                    )
                    service = ProductService(
                        uow, AsyncMock(), AsyncMock(), AsyncMock(), details
                    )
                    kwargs = {"unique_code": "P-001", "batch_id": 42}
                    if fail:
                        with self.assertRaises(RuntimeError):
                            await getattr(service, operation)(**kwargs)
                        self.assertEqual(calls, ["commit"])
                    else:
                        await getattr(service, operation)(**kwargs)
                        self.assertEqual(calls, ["commit", ("invalidate", 42)])


class BatchProductsApiTests(TestCase):
    def test_http_response_includes_short_products(self):
        row = batch(is_closed=False)
        row.products = [product()]
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_batch_service] = lambda: SimpleNamespace(
            get_by_id=AsyncMock(return_value=row)
        )
        with TestClient(app) as client:
            response = client.get("/api/v1/batches/42")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["products"],
            [
                {
                    "id": 15,
                    "unique_code": "P-001",
                    "is_aggregated": False,
                    "aggregated_at": None,
                }
            ],
        )

    def test_repository_loads_products_in_two_queries(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(
            engine, tables=[WorkCenter.__table__, Batch.__table__, Product.__table__]
        )
        with Session(engine) as session:
            center = WorkCenter(name="Center", identifier="RC")
            session.add(center)
            session.flush()
            data = vars(batch(is_closed=False)).copy()
            data["work_center_id"] = center.id
            row = Batch(**data)
            row.products = [Product(unique_code="P-001")]
            session.add(row)
            session.commit()
            session.expunge_all()
            queries = []
            event.listen(
                engine, "before_cursor_execute", lambda *args: queries.append(args[2])
            )
            repository = BatchRepository(
                SimpleNamespace(execute=AsyncMock(side_effect=session.execute))
            )
            import asyncio

            loaded = asyncio.run(repository.get_with_products(42))
            self.assertEqual(len(queries), 2)
            session.expunge_all()
            self.assertEqual(loaded.products[0].unique_code, "P-001")
        engine.dispose()
