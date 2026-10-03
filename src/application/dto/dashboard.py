from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DashboardCounts:
    total_batches: int
    closed_batches: int
    total_products: int
    aggregated_products: int


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    total_batches: int
    open_batches: int
    closed_batches: int
    total_products: int
    aggregated_products: int
    pending_products: int
    aggregation_percent: float
