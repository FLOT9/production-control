from typing import Any, Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(
        self,
        session: AsyncSession,
        model: type[ModelType],
    ) -> None:
        self.session = session
        self.model = model

    async def create(self, **kwargs: Any) -> ModelType:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)

        return instance

    async def get_by_id(self, instance_id: int) -> ModelType | None:
        return await self.session.get(self.model, instance_id)

    async def delete(self, instance: ModelType) -> None:
        await self.session.delete(instance)
        await self.session.flush()
