from unittest import TestCase
from unittest.mock import patch

from src.tasks.product_tasks import aggregate_products


class ProductTaskProgressTests(TestCase):
    def test_progress_explicitly_preserves_task_id_across_thread(self):
        result = {
            "success": True,
            "total": 2,
            "aggregated": 2,
            "failed": 0,
            "errors": [],
        }

        async def process(batch_id, codes, callback):
            self.assertEqual(batch_id, 42)
            self.assertEqual(codes, ["P1", "P2"])
            await callback(1, 2)
            await callback(2, 2)
            return result

        observed = []

        def update(*, task_id, state, meta):
            self.assertIsNone(aggregate_products.request.id)
            observed.append((task_id, state, meta))

        aggregate_products.push_request(id="test-task-id")
        try:
            with (
                patch(
                    "src.tasks.product_tasks._aggregate_products", side_effect=process
                ),
                patch.object(aggregate_products, "update_state", side_effect=update),
            ):
                self.assertEqual(aggregate_products.run(42, ["P1", "P2"]), result)
        finally:
            aggregate_products.pop_request()
        self.assertEqual(
            observed,
            [
                (
                    "test-task-id",
                    "PROGRESS",
                    {"current": 1, "total": 2, "progress": 50},
                ),
                (
                    "test-task-id",
                    "PROGRESS",
                    {"current": 2, "total": 2, "progress": 100},
                ),
            ],
        )
