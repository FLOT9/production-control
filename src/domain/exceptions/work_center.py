class WorkCenterNotFoundError(Exception):
    def __init__(self, work_center_id: int) -> None:
        super().__init__(f"Work center with id={work_center_id} was not found")


class WorkCenterAlreadyExistsError(Exception):
    def __init__(self, identifier: str) -> None:
        super().__init__(f"Work center with identifier={identifier!r} already exists")


class WorkCenterHasBatchesError(Exception):
    def __init__(self, work_center_id: int) -> None:
        super().__init__(f"Work center with id={work_center_id} has related batches")
