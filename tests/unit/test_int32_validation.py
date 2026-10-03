from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from src.api.dependencies.analytics import (
    get_analytics_dashboard_service,
    get_batch_analytics_service,
    get_batch_comparison_service,
)
from src.api.dependencies.batches import get_batch_service
from src.api.dependencies.dashboard import get_dashboard_service
from src.api.dependencies.webhooks import (
    get_webhook_delivery_history_service,
    get_webhook_subscription_service,
)
from src.api.dependencies.work_centers import get_work_center_service
from src.api.v1.routers import api_v1_router
from src.api.v1.schemas.batch import BatchUpdate
from src.api.v1.schemas.common import INT32_MAX, PositiveInt32
from src.application.importers.batch_csv import BatchCsvParser
from src.core.dependencies import get_product_service, get_report_download_service
from tests.unit.test_batch_csv_import import csv_row
from tests.unit.test_batch_integration_api import TZ_ITEM


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(api_v1_router)
    service = AsyncMock()
    for dependency in (
        get_batch_service,
        get_product_service,
        get_work_center_service,
        get_webhook_subscription_service,
        get_webhook_delivery_history_service,
        get_batch_analytics_service,
        get_batch_comparison_service,
        get_analytics_dashboard_service,
        get_dashboard_service,
        get_report_download_service,
    ):
        app.dependency_overrides[dependency] = lambda: service
    with (
        TestClient(app) as client,
        patch("src.api.v1.routers.batches.aggregate_products_task.delay") as aggregate,
        patch("src.api.v1.routers.batches.generate_batch_report_task.delay") as report,
        patch("src.api.v1.routers.batches.export_batches_file_task.delay") as export,
        patch("src.api.v1.routers.batches.export_batches_csv_task.delay") as export_csv,
    ):
        yield client, service, (aggregate, report, export, export_csv)


PATH_REQUESTS = [
    ("GET", "/batches/{id}", None),
    ("PATCH", "/batches/{id}", {}),
    ("DELETE", "/batches/{id}", None),
    ("GET", "/batches/{id}/statistics", None),
    ("POST", "/batches/{id}/aggregate", {"unique_codes": ["A"]}),
    ("POST", "/batches/{id}/aggregate-async", {"unique_codes": ["A"]}),
    ("POST", "/batches/{id}/reports", {}),
    (
        "GET",
        "/batches/{id}/reports/00000000-0000-0000-0000-000000000001/download",
        None,
    ),
    ("GET", "/work-centers/{id}", None),
    ("DELETE", "/work-centers/{id}", None),
    ("GET", "/webhooks/{id}", None),
    ("PATCH", "/webhooks/{id}", {}),
    ("DELETE", "/webhooks/{id}", None),
    ("GET", "/webhooks/{id}/deliveries", None),
    ("GET", "/webhook-subscriptions/{id}", None),
    ("PATCH", "/webhook-subscriptions/{id}", {}),
    ("DELETE", "/webhook-subscriptions/{id}", None),
    ("GET", "/webhook-deliveries/{id}", None),
]


@pytest.mark.parametrize("value", [0, -1, INT32_MAX + 1])
@pytest.mark.parametrize("method,path,body", PATH_REQUESTS)
def test_invalid_path_id_never_reaches_service_or_queue(api, method, path, body, value):
    client, service, tasks = api
    response = client.request(method, "/api/v1" + path.format(id=value), json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "path"
    assert service.mock_calls == []
    for task in tasks:
        task.assert_not_called()


QUERY_REQUESTS = [
    ("GET", "/batches", "batch_number", None),
    ("GET", "/batches", "work_center_id", None),
    ("POST", "/batches/export/csv", "batch_number", None),
    ("POST", "/batches/export/csv", "work_center_id", None),
    ("GET", "/dashboard/summary", "work_center_id", None),
    ("GET", "/analytics/dashboard", "work_center_id", None),
    ("PATCH", "/products/A/aggregate", "batch_id", None),
    ("POST", "/products/aggregate-bulk", "batch_id", {"unique_codes": ["A"]}),
]


@pytest.mark.parametrize("value", [0, -1, INT32_MAX + 1])
@pytest.mark.parametrize("method,path,name,body", QUERY_REQUESTS)
def test_invalid_query_id_never_reaches_service_or_queue(
    api, method, path, name, body, value
):
    client, service, tasks = api
    response = client.request(method, "/api/v1" + path, params={name: value}, json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", name]
    assert service.mock_calls == []
    for task in tasks:
        task.assert_not_called()


@pytest.mark.parametrize("value", [0, -1, INT32_MAX + 1])
def test_json_fields_and_list_elements_are_validated_before_execution(api, value):
    client, service, tasks = api
    requests = [
        ("POST", "/products", {"unique_code": "A", "batch_id": value}),
        ("POST", "/batches", [{**TZ_ITEM, "НомерПартии": value}]),
        ("PATCH", "/batches/1", {"batch_number": value}),
        ("PATCH", "/batches/1", {"work_center_id": value}),
        ("POST", "/batches/export", {"filters": {"batch_number": value}}),
        ("POST", "/batches/export", {"filters": {"work_center_id": value}}),
        ("POST", "/analytics/compare-batches", {"batch_ids": [1, value]}),
    ]
    for method, path, body in requests:
        response = client.request(method, "/api/v1" + path, json=body)
        assert response.status_code == 422, (method, path, response.text)
        assert response.json()["detail"][0]["loc"][0] == "body"
    response = client.get(
        "/api/v1/batches/compare", params=[("batch_ids", 1), ("batch_ids", value)]
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "batch_ids", 1]
    assert service.mock_calls == []
    for task in tasks:
        task.assert_not_called()


@pytest.mark.parametrize("value", [1, INT32_MAX])
def test_valid_path_boundaries_reach_business_not_found(api, value):
    client, service, _ = api
    service.get_by_id.side_effect = HTTPException(status_code=404, detail="Not found")
    response = client.get(f"/api/v1/batches/{value}")
    assert response.status_code == 404
    service.get_by_id.assert_awaited_once_with(value)
    assert TypeAdapter(PositiveInt32).validate_python(value) == value


@pytest.mark.parametrize("value", [1, INT32_MAX])
def test_query_boundaries_and_omitted_filters_are_accepted(api, value):
    client, service, _ = api
    service.list_batches.return_value = ([], 0)
    response = client.get(
        "/api/v1/batches", params={"batch_number": value, "work_center_id": value}
    )
    assert response.status_code == 200
    filters = service.list_batches.await_args.kwargs["filters"]
    assert filters.batch_number == filters.work_center_id == value
    assert client.get("/api/v1/batches").status_code == 200
    filters = service.list_batches.await_args.kwargs["filters"]
    assert filters.batch_number is filters.work_center_id is None


def test_patch_preserves_omitted_vs_null_and_accepts_boundaries():
    assert BatchUpdate().model_dump(exclude_unset=True) == {}
    for name in ("batch_number", "work_center_id"):
        with pytest.raises(ValidationError, match="cannot be null"):
            BatchUpdate(**{name: None})
        for value in (1, INT32_MAX):
            update = BatchUpdate(**{name: value})
            assert update.model_fields_set == {name}
            assert update.model_dump(exclude_unset=True) == {name: value}


def test_csv_overflow_is_row_error_and_next_row_is_processed():
    content = csv_row().decode().splitlines()
    headers = content[0].split(";")
    for name in ("batch_number", "work_center_id"):
        invalid = content[1].split(";")
        invalid[headers.index(name)] = str(INT32_MAX + 1)
        csv = (
            content[0] + "\n" + ";".join(invalid) + "\n" + content[1] + "\n"
        ).encode()
        parsed = BatchCsvParser().parse(csv)
        assert len(parsed.errors) == len(parsed.valid_rows) == 1
        assert parsed.errors[0].row_number == 2
        assert name in parsed.errors[0].reason
