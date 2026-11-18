from typing import Annotated

from fastapi import Path, Query

from src.application.dto.common import INT32_MAX, PositiveInt32

__all__ = [
    "INT32_MAX",
    "OptionalPositiveInt32Query",
    "PositiveInt32",
    "PositiveInt32Path",
    "PositiveInt32Query",
]

PositiveInt32Path = Annotated[int, Path(gt=0, le=INT32_MAX)]
PositiveInt32Query = Annotated[int, Query(gt=0, le=INT32_MAX)]
OptionalPositiveInt32Query = Annotated[int | None, Query(gt=0, le=INT32_MAX)]
