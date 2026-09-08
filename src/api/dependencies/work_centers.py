from typing import Annotated

from fastapi import Depends

from src.application.services.work_center_command_service import (
    WorkCenterCommandService,
)
from src.application.services.work_center_query_service import WorkCenterQueryService
from src.core.dependencies import (
    get_work_center_command_service,
    get_work_center_query_service,
    get_work_center_service,
)
from src.domain.services.work_center_service import WorkCenterService

WorkCenterServiceDep = Annotated[
    WorkCenterService,
    Depends(get_work_center_service),
]

WorkCenterQueryServiceDep = Annotated[
    WorkCenterQueryService,
    Depends(get_work_center_query_service),
]

WorkCenterCommandServiceDep = Annotated[
    WorkCenterCommandService,
    Depends(get_work_center_command_service),
]
