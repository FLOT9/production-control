class ProductAlreadyExistsError(Exception):
    def __init__(self, unique_code: str) -> None:
        super().__init__(f"Product with unique_code={unique_code!r} already exists")


class ProductNotFoundError(Exception):
    def __init__(self, unique_code: str) -> None:
        super().__init__(f"Product with unique_code={unique_code!r} not found")
