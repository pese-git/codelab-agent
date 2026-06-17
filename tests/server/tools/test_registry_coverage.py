"""Тесты покрытия непокрытых веток SimpleToolRegistry."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.registry import SimpleToolRegistry


@pytest.fixture
def registry() -> SimpleToolRegistry:
    """Создаёт пустой реестр инструментов."""
    return SimpleToolRegistry()


class TestRegistryAvailableTools:
    """Тесты фильтрации доступных инструментов."""

    def test_get_available_tools_excludes_permission_required(
        self,
        registry: SimpleToolRegistry,
    ) -> None:
        """Фильтр исключает инструменты, требующие разрешения (строка 148)."""
        registry.register_tool(
            name="allowed",
            description="Allowed tool",
            parameters={},
            kind="other",
            executor=lambda: "ok",
            requires_permission=False,
        )
        registry.register_tool(
            name="restricted",
            description="Restricted tool",
            parameters={},
            kind="other",
            executor=lambda: "ok",
            requires_permission=True,
        )

        tools = registry.get_available_tools("session", include_permission_required=False)

        assert len(tools) == 1
        assert tools[0].name == "allowed"


class TestRegistryExecuteToolNotFound:
    """Тесты обработки отсутствующего инструмента в execute_tool."""

    @pytest.mark.asyncio
    async def test_execute_tool_unknown_logs_error(
        self,
        registry: SimpleToolRegistry,
    ) -> None:
        """Неизвестный инструмент логирует ошибку и возвращает результат (строки 201-207)."""
        with patch("codelab.server.tools.registry.logger") as mock_logger:
            result = await registry.execute_tool("session", "unknown_tool", {})

        assert result.success is False
        assert result.error is not None
        assert "unknown_tool" in result.error
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args.kwargs
        assert call_kwargs["tool_name"] == "unknown_tool"
        assert call_kwargs["acp_tool_name"] == "unknown_tool"


class TestRegistryExecuteToolAsyncSession:
    """Тесты async executor с передачей session."""

    @pytest.mark.asyncio
    async def test_execute_tool_async_with_session_param(
        self,
        registry: SimpleToolRegistry,
    ) -> None:
        """Async executor получает session, если принимает её (строка 235)."""
        async def async_handler(session: SessionState, value: int) -> ToolExecutionResult:
            return ToolExecutionResult(
                success=True,
                output=f"session={session.session_id} value={value}",
            )

        registry.register_tool(
            name="async_with_session",
            description="Async handler with session",
            parameters={},
            kind="other",
            executor=async_handler,
        )

        session = SessionState(session_id="s1", cwd="/tmp", mcp_servers=[])
        result = await registry.execute_tool(
            "session",
            "async_with_session",
            {"value": 42},
            session=session,
        )

        assert result.success is True
        assert result.output == "session=s1 value=42"


class TestRegistryExecuteToolException:
    """Тесты обработки исключений в execute_tool."""

    @pytest.mark.asyncio
    async def test_execute_tool_sync_exception(
        self,
        registry: SimpleToolRegistry,
    ) -> None:
        """Исключение синхронного executor оборачивается в результат (строки 264-274)."""
        def failing_handler() -> str:
            raise RuntimeError("boom")

        registry.register_tool(
            name="failing",
            description="Failing tool",
            parameters={},
            kind="other",
            executor=failing_handler,
        )

        with patch("codelab.server.tools.registry.logger") as mock_logger:
            result = await registry.execute_tool("session", "failing", {})

        assert result.success is False
        assert result.error is not None
        assert "boom" in result.error
        mock_logger.error.assert_called_once()
