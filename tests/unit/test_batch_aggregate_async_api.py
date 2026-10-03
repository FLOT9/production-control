from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.routers.batches import router


class BatchAggregateAsyncApiTests(TestCase):
    def test_enqueues_batch_and_codes_and_returns_task_id(self) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        with (
            patch(
                "src.api.v1.routers.batches.aggregate_products_task.delay",
                return_value=SimpleNamespace(id="test-task-id"),
            ) as delay,
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/v1/batches/42/aggregate-async",
                json={"unique_codes": ["P1", "P2"]},
            )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(
                response.json(), {"task_id": "test-task-id", "status": "queued"}
            )
            delay.assert_called_once_with(batch_id=42, unique_codes=["P1", "P2"])

            delay.reset_mock()
            invalid = client.post(
                "/api/v1/batches/42/aggregate-async", json={"unique_codes": []}
            )
            self.assertEqual(invalid.status_code, 422)
            delay.assert_not_called()
