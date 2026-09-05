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
