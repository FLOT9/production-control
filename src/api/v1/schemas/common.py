from typing import Annotated

from fastapi import Path, Query
from pydantic import Field

INT32_MAX = 2**31 - 1

PositiveInt32 = Annotated[int, Field(gt=0, le=INT32_MAX)]
PositiveInt32Path = Annotated[int, Path(gt=0, le=INT32_MAX)]
PositiveInt32Query = Annotated[int, Query(gt=0, le=INT32_MAX)]
OptionalPositiveInt32Query = Annotated[int | None, Query(gt=0, le=INT32_MAX)]
