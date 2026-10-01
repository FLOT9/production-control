class ProductAlreadyExistsError(Exception):
    def __init__(self, unique_code: str) -> None:
        super().__init__(f"Product with unique_code={unique_code!r} already exists")


class ProductNotFoundError(Exception):
    def __init__(self, unique_code: str) -> None:
        super().__init__(f"Product with unique_code={unique_code!r} not found")


class ProductAlreadyAggregatedError(Exception):
    def __init__(self, unique_code: str) -> None:
        super().__init__(f"Product with unique_code={unique_code!r} already aggregated")


class ProductBatchMismatchError(Exception):
    def __init__(
        self, unique_code: str, expected_batch_id: int, actual_batch_id: int
    ) -> None:
        super().__init__(
            f"Product with unique_code={unique_code!r} belongs to "
            f"batch_id={actual_batch_id}, expected batch_id={expected_batch_id}"
        )
