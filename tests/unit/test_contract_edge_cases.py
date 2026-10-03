from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from src.api.v1.schemas.product import ProductAggregationRequest
from src.api.v1.schemas.webhook import (
    WebhookSubscriptionCreate,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
)
from src.application.exceptions import ProductionSummaryEmptyError
from src.tasks.task_status import get_task_status
from tests.unit.test_batch_details_cache import batch


def test_aggregation_has_bounded_request_size():
    assert (
        len(
            ProductAggregationRequest(
                unique_codes=[str(i) for i in range(1000)]
            ).unique_codes
        )
        == 1000
    )
    with pytest.raises(ValidationError):
        ProductAggregationRequest(unique_codes=[str(i) for i in range(1001)])


def test_timeout_contract_and_legacy_input_preserve_patch_semantics():
    for name in ("timeout", "timeout_seconds"):
        payload = WebhookSubscriptionCreate(
            url="https://example.com",
            events=["batch_created"],
            secret_key="x" * 32,
            **{name: 12},
        )
        assert payload.timeout_seconds == 12
        update = WebhookSubscriptionUpdate(**{name: 12})
        assert update.model_dump(exclude_unset=True, by_alias=False) == {
            "timeout_seconds": 12
        }
        with pytest.raises(ValidationError):
            WebhookSubscriptionUpdate(**{name: None})
    assert WebhookSubscriptionUpdate().model_dump(exclude_unset=True) == {}
    now = batch(is_closed=False).created_at
    response = WebhookSubscriptionRead(
        id=1,
        url="https://example.com",
        events=["batch_created"],
        is_active=True,
        retry_count=3,
        timeout_seconds=12,
        created_at=now,
        updated_at=now,
    )
    assert response.model_dump(by_alias=True)["timeout"] == 12


def test_empty_summary_has_clear_public_task_error():
    task = SimpleNamespace(
        id="empty",
        backend=SimpleNamespace(
            get_task_meta=Mock(
                return_value={
                    "status": "FAILURE",
                    "result": ProductionSummaryEmptyError(),
                }
            )
        ),
    )
    with patch("src.tasks.task_status.celery_app.AsyncResult", return_value=task):
        assert (
            get_task_status("empty")["error"]
            == "No production data available for report"
        )


def test_exports_bucket_receives_retention_rules():
    from scripts.init_minio import main

    client = Mock()
    client.bucket_exists.return_value = True
    client.get_bucket_lifecycle.return_value = None
    with (
        patch("scripts.init_minio.Minio", return_value=client),
        patch.dict(
            "os.environ",
            {
                "MINIO_ENDPOINT": "minio:9000",
                "MINIO_ROOT_USER": "user",
                "MINIO_ROOT_PASSWORD": "password",
            },
        ),
    ):
        main()
    export = next(
        call
        for call in client.set_bucket_lifecycle.call_args_list
        if call.args[0] == "exports"
    )
    assert export.args[1].rules[0].rule_filter.prefix == "batch-exports/"
    assert export.args[1].rules[0].expiration.days == 7


def test_empty_summary_exception_survives_celery_serialization():
    from src.tasks.celery_app import celery_app

    backend = celery_app.backend
    restored = backend.exception_to_python(
        backend.prepare_exception(ProductionSummaryEmptyError())
    )
    assert isinstance(restored, ProductionSummaryEmptyError)
    assert str(restored) == "No production data available for report"
