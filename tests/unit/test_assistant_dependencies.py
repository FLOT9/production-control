import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy.exc import OperationalError, ProgrammingError

from src.application.ai.exceptions import AssistantDataUnavailableError
from src.core.assistant_dependencies import batch_analytics_service


class AssistantDependenciesTests(IsolatedAsyncioTestCase):
    async def test_database_error_is_translated_and_resources_close(self):
        session = Mock()
        context = Mock()
        context.__aenter__ = AsyncMock(return_value=session)
        context.__aexit__ = AsyncMock(return_value=False)
        redis = Mock()
        redis.aclose = AsyncMock()
        error = OperationalError("query", {}, Exception("private DB details"))
        with (
            patch(
                "src.core.assistant_dependencies.async_session_maker",
                return_value=context,
            ),
            patch(
                "src.core.assistant_dependencies.create_redis_client",
                return_value=redis,
            ),
            self.assertRaises(AssistantDataUnavailableError) as raised,
        ):
            async with batch_analytics_service():
                raise error
        self.assertIs(raised.exception.__cause__, error)
        self.assertNotIn("private", str(raised.exception))
        context.__aexit__.assert_awaited_once()
        redis.aclose.assert_awaited_once()

    async def test_programming_error_is_not_translated(self):
        context = Mock()
        context.__aenter__ = AsyncMock(return_value=Mock())
        context.__aexit__ = AsyncMock(return_value=False)
        redis = Mock()
        redis.aclose = AsyncMock()
        with (
            patch(
                "src.core.assistant_dependencies.async_session_maker",
                return_value=context,
            ),
            patch(
                "src.core.assistant_dependencies.create_redis_client",
                return_value=redis,
            ),
            self.assertRaisesRegex(ValueError, "bug"),
        ):
            async with batch_analytics_service():
                raise ValueError("bug")
        redis.aclose.assert_awaited_once()

    async def test_sql_programming_error_and_cancellation_survive_cleanup_failure(self):
        for error in (
            ProgrammingError("invalid SQL", {}, Exception("bug")),
            asyncio.CancelledError(),
        ):
            with self.subTest(error=type(error).__name__):
                context = Mock()
                context.__aenter__ = AsyncMock(return_value=Mock())
                context.__aexit__ = AsyncMock(return_value=False)
                redis = Mock()
                redis.aclose = AsyncMock(side_effect=OSError("close failed"))
                with (
                    patch(
                        "src.core.assistant_dependencies.async_session_maker",
                        return_value=context,
                    ),
                    patch(
                        "src.core.assistant_dependencies.create_redis_client",
                        return_value=redis,
                    ),
                    self.assertRaises(type(error)) as raised,
                ):
                    async with batch_analytics_service():
                        raise error
                self.assertIs(raised.exception, error)
                context.__aexit__.assert_awaited_once()
                redis.aclose.assert_awaited_once()
