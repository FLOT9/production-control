from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BatchProductCounts:
    batch_id: int
    total_products: int
    aggregated_products: int


@dataclass(frozen=True, slots=True)
class BatchStatistics:
    batch_id: int
    total_products: int
    aggregated_products: int
    pending_products: int
    aggregation_percent: float
