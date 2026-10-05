from datetime import UTC, datetime
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError

from src.api.v1.schemas.batch import BatchIntegrationItem
from src.core.config import settings


def integration_payload(start: str) -> dict[str, object]:
    return {
        "СтатусЗакрытия": False,
        "ПредставлениеЗаданияНаСмену": "Выпуск деталей",
        "РабочийЦентр": "Линия 1",
        "ИдентификаторРЦ": "WC-1",
        "Смена": "Дневная",
        "Бригада": "Бригада 1",
        "НомерПартии": 12,
        "ДатаПартии": "2026-09-30",
        "Номенклатура": "Деталь",
        "КодЕКН": "EKN-1",
        "ДатаВремяНачалаСмены": start,
        "ДатаВремяОкончанияСмены": "2026-09-30T20:00:00",
    }


class BatchIntegrationSchemaTests(TestCase):
    def test_naive_datetime_uses_configured_production_timezone(self):
        for timezone, expected_hour in [("Asia/Yekaterinburg", 3), ("UTC", 8)]:
            with (
                self.subTest(timezone=timezone),
                patch.object(settings, "production_timezone", timezone),
            ):
                item = BatchIntegrationItem.model_validate(
                    integration_payload("2026-09-30T08:00:00")
                )
                self.assertEqual(
                    item.shift_start, datetime(2026, 9, 30, expected_hour, tzinfo=UTC)
                )
                self.assertIs(item.shift_start.tzinfo, UTC)

    def test_explicit_offset_is_preserved_as_an_instant(self):
        with patch.object(settings, "production_timezone", "Asia/Yekaterinburg"):
            item = BatchIntegrationItem.model_validate(
                integration_payload("2026-09-30T08:00:00+03:00")
            )
        self.assertEqual(item.shift_start, datetime(2026, 9, 30, 5, tzinfo=UTC))

    def test_timezone_conversion_can_change_the_calendar_day(self):
        with patch.object(settings, "production_timezone", "Asia/Yekaterinburg"):
            item = BatchIntegrationItem.model_validate(
                integration_payload("2026-09-30T02:00:00")
            )
        self.assertEqual(item.shift_start, datetime(2026, 9, 29, 21, tzinfo=UTC))

    def test_invalid_timezone_is_rejected_in_configuration(self):
        with self.assertRaises(ValidationError):
            type(settings)(production_timezone="Invalid/Timezone")

    def test_mixed_timezone_inputs_are_compared_after_normalization(self):
        payload = integration_payload("2026-09-30T08:00:00+03:00")
        payload["ДатаВремяОкончанияСмены"] = "2026-09-30T09:00:00"
        with (
            patch.object(settings, "production_timezone", "Asia/Yekaterinburg"),
            self.assertRaises(ValidationError),
        ):
            BatchIntegrationItem.model_validate(payload)

    def test_english_names_and_russian_keys_produce_same_data(self):
        item = BatchIntegrationItem.model_validate(
            integration_payload("2026-09-30T08:00:00")
        )
        self.assertEqual(BatchIntegrationItem.model_validate(item.model_dump()), item)
