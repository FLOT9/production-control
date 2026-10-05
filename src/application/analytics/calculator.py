from datetime import datetime, timedelta
from statistics import mean

from src.application.dto.analytics import (
    BatchAnalytics,
    BatchAnalyticsSnapshot,
    BatchComparison,
    BatchComparisonItem,
    BatchTimeline,
    ComparisonAverage,
    DashboardMetrics,
    ForecastStatus,
    ProductMetrics,
    TeamPerformance,
)


def product_metrics(total: int, aggregated: int) -> ProductMetrics:
    return ProductMetrics(
        total_products=total,
        aggregated_products=aggregated,
        pending_products=total - aggregated,
        aggregation_percent=round(aggregated / total * 100, 2) if total else 0.0,
    )


def dashboard_metrics(
    total_batches: int, closed_batches: int, total: int, aggregated: int
) -> DashboardMetrics:
    return DashboardMetrics(
        **product_metrics(total, aggregated).model_dump(),
        total_batches=total_batches,
        closed_batches=closed_batches,
        open_batches=total_batches - closed_batches,
    )


def batch_timeline(snapshot: BatchAnalyticsSnapshot, now: datetime) -> BatchTimeline:
    info = snapshot.batch_info
    duration = max((info.shift_end - info.shift_start).total_seconds() / 3600, 0.0)
    end = min(now, info.shift_end)
    if info.is_closed and info.closed_at is not None:
        end = min(end, info.closed_at)
    elapsed = max((end - info.shift_start).total_seconds() / 3600, 0.0)
    rate = snapshot.window_products / elapsed if elapsed else None
    remaining = snapshot.total_products - snapshot.aggregated_products
    completion = None
    status: ForecastStatus
    if snapshot.total_products == 0:
        status = "no_products"
    elif now < info.shift_start:
        status = "not_started"
    elif remaining == 0:
        status = "completed"
        completion = snapshot.last_aggregated_at
    elif info.is_closed:
        status = "batch_closed"
    elif now >= info.shift_end:
        status = "shift_finished"
    elif not rate:
        status = "no_progress"
    else:
        status = "available"
        # Cap pathological estimates so invalidly tiny elapsed intervals cannot overflow datetime.
        seconds = min(
            remaining / rate * 3600,
            (datetime.max.replace(tzinfo=now.tzinfo) - now).total_seconds() - 1,
        )
        completion = now + timedelta(seconds=seconds)
    return BatchTimeline(
        duration_hours=round(duration, 4),
        elapsed_hours=round(elapsed, 4),
        products_per_hour=round(rate, 2) if rate is not None else None,
        estimated_completion_at=completion,
        forecast_status=status,
    )


def batch_analytics(snapshot: BatchAnalyticsSnapshot, now: datetime) -> BatchAnalytics:
    metrics = product_metrics(snapshot.total_products, snapshot.aggregated_products)
    timeline = batch_timeline(snapshot, now)
    return BatchAnalytics(
        **metrics.model_dump(),
        batch_id=snapshot.batch_info.id,
        batch_info=snapshot.batch_info,
        timeline=timeline,
        team_performance=TeamPerformance(
            **metrics.model_dump(),
            team=snapshot.batch_info.team,
            products_per_hour=timeline.products_per_hour,
        ),
        cached_at=snapshot.cached_at,
    )


def compare_batches(snapshots: list[BatchAnalyticsSnapshot]) -> BatchComparison:
    items = []
    durations = []
    rates = []
    for snapshot in snapshots:
        info = snapshot.batch_info
        duration = max((info.shift_end - info.shift_start).total_seconds() / 3600, 0.0)
        rate = snapshot.aggregated_products / duration if duration else 0.0
        durations.append(duration)
        rates.append(rate)
        items.append(
            BatchComparisonItem(
                **product_metrics(
                    snapshot.total_products, snapshot.aggregated_products
                ).model_dump(),
                batch_info=info,
                duration_hours=round(duration, 4),
                products_per_hour=round(rate, 2),
            )
        )
    return BatchComparison(
        items=items,
        average=ComparisonAverage(
            duration_hours=round(mean(durations), 4),
            total_products=round(mean(item.total_products for item in items), 2),
            aggregated_products=round(
                mean(item.aggregated_products for item in items), 2
            ),
            pending_products=round(mean(item.pending_products for item in items), 2),
            aggregation_percent=round(
                mean(item.aggregation_percent for item in items), 2
            ),
            products_per_hour=round(mean(rates), 2),
        ),
        overall_products_per_hour=round(
            sum(item.aggregated_products for item in items) / sum(durations), 2
        )
        if sum(durations)
        else 0.0,
    )
