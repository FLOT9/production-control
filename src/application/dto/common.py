from typing import Annotated

from pydantic import Field

INT32_MAX = 2**31 - 1
PositiveInt32 = Annotated[int, Field(gt=0, le=INT32_MAX)]
