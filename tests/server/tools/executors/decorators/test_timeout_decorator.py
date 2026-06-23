"""Тесты для TimeoutDecorator."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from codelab.server.mcp.exceptions import MCPTimeoutError
from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.decorators import TimeoutDecorator


class MockExecutor:
    """Mock executor для тестирования."""
    
    def __init__(self, result: ToolExecutionResult | None = None, delay: float = 0.0) -> None:
        self.result = result or ToolExecutionResult(success=True, output="test")
        self.delay = delay
        self.call_count = 0
    
    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        self.call_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return self.result


@pytest.fixture
def mock_session() -> SessionState:
    """Создать mock сессию."""
    session = MagicMock(spec=SessionState)
    session.session_id = "test_session"
    return session


@pytest.fixture
def mock_arguments() -> dict[str, Any]:
    """Создать mock аргументы."""
    return {"tool_name": "mcp:server:tool", "arg1": "value1"}


class TestTimeoutDecorator:
    """Тесты для TimeoutDecorator."""
    
    @pytest.mark.asyncio
    async def test_execute_success_within_timeout(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Успешное выполнение в пределах timeout."""
        mock_executor = MockExecutor(delay=0.1)
        decorator = TimeoutDecorator(mock_executor, timeout=1.0)
        
        result = await decorator.execute(mock_session, mock_arguments)
        
        assert result.success is True
        assert result.output == "test"
        assert mock_executor.call_count == 1
    
    @pytest.mark.asyncio
    async def test_execute_timeout_exceeded(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Превышение timeout генерирует MCPTimeoutError."""
        mock_executor = MockExecutor(delay=2.0)
        decorator = TimeoutDecorator(mock_executor, timeout=0.1)
        
        with pytest.raises(MCPTimeoutError) as exc_info:
            await decorator.execute(mock_session, mock_arguments)
        
        assert exc_info.value.tool_name == "mcp:server:tool"
        assert exc_info.value.timeout == 0.1
    
    @pytest.mark.asyncio
    async def test_execute_with_custom_timeout(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Кастомный timeout корректно применяется."""
        mock_executor = MockExecutor(delay=0.5)
        decorator = TimeoutDecorator(mock_executor, timeout=0.3)
        
        with pytest.raises(MCPTimeoutError) as exc_info:
            await decorator.execute(mock_session, mock_arguments)
        
        assert exc_info.value.timeout == 0.3
    
    @pytest.mark.asyncio
    async def test_execute_preserves_result(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Результат выполнения сохраняется."""
        expected_result = ToolExecutionResult(
            success=True,
            output="custom output",
            raw_output={"key": "value"},
        )
        mock_executor = MockExecutor(result=expected_result)
        decorator = TimeoutDecorator(mock_executor, timeout=1.0)
        
        result = await decorator.execute(mock_session, mock_arguments)
        
        assert result.success == expected_result.success
        assert result.output == expected_result.output
        assert result.raw_output == expected_result.raw_output
    
    @pytest.mark.asyncio
    async def test_execute_with_error_result(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Ошибка в результате не вызывает исключение."""
        error_result = ToolExecutionResult(
            success=False,
            error="Tool execution failed",
        )
        mock_executor = MockExecutor(result=error_result)
        decorator = TimeoutDecorator(mock_executor, timeout=1.0)
        
        result = await decorator.execute(mock_session, mock_arguments)
        
        assert result.success is False
        assert "failed" in result.error
    
    @pytest.mark.asyncio
    async def test_default_timeout_is_30_seconds(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Default timeout равен 30 секундам."""
        mock_executor = MockExecutor()
        decorator = TimeoutDecorator(mock_executor)
        
        assert decorator._timeout == 30.0
    
    @pytest.mark.asyncio
    async def test_timeout_error_contains_tool_name(
        self,
        mock_session: SessionState,
    ) -> None:
        """MCPTimeoutError содержит имя инструмента."""
        mock_executor = MockExecutor(delay=2.0)
        decorator = TimeoutDecorator(mock_executor, timeout=0.1)
        
        arguments = {"tool_name": "mcp:filesystem:read_file", "path": "/test"}
        
        with pytest.raises(MCPTimeoutError) as exc_info:
            await decorator.execute(mock_session, arguments)
        
        assert exc_info.value.tool_name == "mcp:filesystem:read_file"
