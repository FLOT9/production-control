from dataclasses import asdict
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies.batches import get_batch_service
from src.api.exception_handlers import register_exception_handlers
from src.api.v1.routers.batches import router
from src.application.dto import BatchIntegrationData
from src.core.config import settings
from src.domain.exceptions.batch import BatchAlreadyExistsError

TZ_ITEM = {
    "СтатусЗакрытия": False,
    "ПредставлениеЗаданияНаСмену": "Изготовить 1000 болтов М10",
    "РабочийЦентр": "Цех №1",
    "Смена": "1 смена",
    "Бригада": "Бригада Иванова",
    "НомерПартии": 22222,
    "ДатаПартии": "2024-01-30",
    "Номенклатура": "Болт М10х50",
    "КодЕКН": "EKN-12345",
    "ИдентификаторРЦ": "RC-001",
    "ДатаВремяНачалаСмены": "2024-01-30T08:00:00",
    "ДатаВремяОкончанияСмены": "2024-01-30T20:00:00",
}


class BatchIntegrationApiTests(TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        register_exception_handlers(app)
        self.service = SimpleNamespace(create_many=AsyncMock(side_effect=self.created))
        app.dependency_overrides[get_batch_service] = lambda: self.service
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        timezone_patch = patch.object(
            settings, "production_timezone", "Asia/Yekaterinburg"
        )
        timezone_patch.start()
        self.addCleanup(timezone_patch.stop)

    @staticmethod
    def created(items):
        result = []
        for index, item in enumerate(items, start=1):
            data = asdict(item)
            data.pop("work_center_name")
            data.pop("work_center_identifier")
            now = datetime.now(UTC)
            result.append(
                SimpleNamespace(
                    **data,
                    id=index,
                    work_center_id=10,
                    closed_at=now if item.is_closed else None,
                    created_at=now,
                    updated_at=now,
                )
            )
        return result

    def test_exact_tz_payload_returns_array_and_passes_normalized_data_to_service(self):
        response = self.client.post("/api/v1/batches", json=[TZ_ITEM])
        self.assertEqual(response.status_code, 201)
        self.assertIsInstance(response.json(), list)
        batch = response.json()[0]
        self.assertEqual(batch["batch_number"], 22222)
        self.assertEqual(batch["work_center_id"], 10)
        self.assertEqual(batch["shift_start"], "2024-01-30T03:00:00Z")
        self.assertEqual(batch["shift_end"], "2024-01-30T15:00:00Z")
        self.service.create_many.assert_awaited_once()
        item = self.service.create_many.await_args.args[0][0]
        self.assertIsInstance(item, BatchIntegrationData)
        self.assertEqual(item.work_center_identifier, "RC-001")
        self.assertEqual(item.work_center_name, "Цех №1")
        self.assertEqual(item.batch_date, date(2024, 1, 30))

    def test_multiple_items_and_initial_closed_state_are_forwarded(self):
        response = self.client.post(
            "/api/v1/batches",
            json=[TZ_ITEM, {**TZ_ITEM, "НомерПартии": 22223, "СтатусЗакрытия": True}],
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()), 2)
        self.assertTrue(response.json()[1]["is_closed"])
        self.assertIsNotNone(response.json()[1]["closed_at"])

    def test_invalid_request_is_rejected_before_service_is_called(self):
        for payload in [
            TZ_ITEM,
            [],
            [TZ_ITEM] * 1001,
            [{**TZ_ITEM, "НомерПартии": 2**31}],
            [{**TZ_ITEM, "РабочийЦентр": "   "}],
            [{**TZ_ITEM, "ДатаВремяОкончанияСмены": "2024-01-30T07:00:00"}],
        ]:
            with self.subTest(payload_type=type(payload).__name__):
                response = self.client.post("/api/v1/batches", json=payload)
                self.assertEqual(response.status_code, 422)
        self.service.create_many.assert_not_awaited()

    def test_duplicate_batch_returns_409(self):
        self.service.create_many.side_effect = BatchAlreadyExistsError(
            22222, date(2024, 1, 30)
        )
        response = self.client.post("/api/v1/batches", json=[TZ_ITEM])
        self.assertEqual(response.status_code, 409)
