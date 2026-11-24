from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.application.ai.schemas import AggregationDayArgs


def resolve_aggregation_day(
    value: date | str, now: datetime, timezone: ZoneInfo
) -> date:
    if isinstance(value, date):
        return value

    local_today = now.astimezone(timezone).date()
    if value == "yesterday":
        return local_today - timedelta(days=1)
    if value == "today":
        return local_today

    raise ValueError("Unknown aggregation day")


def resolve_aggregation_range(
    request: AggregationDayArgs, now: datetime, timezone: ZoneInfo
) -> tuple[date, date]:
    if request.day is not None:
        day = resolve_aggregation_day(request.day, now, timezone)
        return day, day
    if request.period == "last_week":
        today = now.astimezone(timezone).date()
        monday = today - timedelta(days=today.weekday() + 7)
        return monday, monday + timedelta(days=6)
    if request.date_from is None or request.date_to is None:
        raise ValueError("Date range requires both bounds")
    return request.date_from, request.date_to
