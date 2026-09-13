from datetime import date


class BatchNotFoundError(Exception):
    def __init__(self, batch_id: int) -> None:
        super().__init__(f"Batch with id={batch_id} was not found")


class BatchAlreadyExistsError(Exception):
    def __init__(
        self,
        batch_number: int,
        batch_date: date,
    ) -> None:
        super().__init__(
            f"Batch number={batch_number} on date={batch_date} already exists"
        )


class BatchClosedError(Exception):
    def __init__(self, batch_id: int) -> None:
        super().__init__(f"Batch with id={batch_id} is closed")


class BatchInvalidShiftPeriodError(Exception):
    def __init__(self) -> None:
        super().__init__("shift_end must be later than shift_start")


class BatchHasProductsError(Exception):
    def __init__(self, batch_id: int) -> None:
        super().__init__(f"Batch with id={batch_id} has products and cannot be deleted")
