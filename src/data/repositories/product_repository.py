from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import Product
from src.data.repositories.base_repository import BaseRepository


class ProductRepository(BaseRepository[Product]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Product)

    async def get_by_unique_code(
        self,
        unique_code: str,
    ) -> Product | None:
        statement = select(Product).where(Product.unique_code == unique_code)
        product = await self.session.execute(statement)

        return product.scalar_one_or_none()

    async def get_by_unique_code_for_update(
        self,
        unique_code: str,
    ) -> Product | None:
        statement = (
            select(Product).where(Product.unique_code == unique_code).with_for_update()
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def exists_by_batch_id(self, batch_id: int) -> bool:
        statement = select(exists().where(Product.batch_id == batch_id))
        return bool(await self.session.scalar(statement))
