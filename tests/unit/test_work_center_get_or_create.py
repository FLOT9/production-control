from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from src.data.models import WorkCenter
from src.data.repositories.work_center_repository import WorkCenterRepository


class WorkCenterGetOrCreateTests(IsolatedAsyncioTestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        WorkCenter.__table__.create(engine)
        self.session = Session(engine)
        self.addCleanup(self.session.close)
        # Execute real SQL; adapt the synchronous session to the async interface.
        self.repository = WorkCenterRepository(
            SimpleNamespace(
                scalar=AsyncMock(side_effect=self.session.scalar),
                execute=AsyncMock(side_effect=self.session.execute),
            )
        )

    async def test_missing_center_is_created(self):
        center = await self.repository.get_or_create_by_identifier("WC-1", "Line 1")
        self.assertIsNotNone(center.id)
        self.assertEqual(center.identifier, "WC-1")
        self.assertEqual(center.name, "Line 1")
        self.assertIsNotNone(center.created_at)

    async def test_same_identifier_reuses_existing_center_without_renaming(self):
        first = await self.repository.get_or_create_by_identifier("WC-1", "Line 1")
        self.session.commit()
        second = await self.repository.get_or_create_by_identifier("WC-1", "New name")
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.name, "Line 1")
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(WorkCenter)), 1
        )

    async def test_creation_is_rolled_back_with_the_outer_transaction(self):
        await self.repository.get_or_create_by_identifier("WC-1", "Line 1")
        self.session.rollback()
        self.assertIsNone(
            self.session.scalar(
                select(WorkCenter).where(WorkCenter.identifier == "WC-1")
            )
        )
