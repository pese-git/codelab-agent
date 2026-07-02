"""Тесты для RetryDecorator."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from codelab.server.mcp.exceptions import (
    MCPConnectionError,
    MCPServerError,
    MCPTimeoutError,
    MCPValidationError,
)
from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.decorators import RetryDecorator


class MockExecutor:
    """Mock executor для тестирования retry логики."""
    
    def __init__(
        self,
        fail_count: int = 0,
        error_type: type[Exception] | None = None,
        result: ToolExecutionResult | None = None,
    ) -> None:
        """Инициализация mock executor.
        
        Args:
            fail_count: Количество неудачных попыток перед успехом.
            error_type: Тип ошибки для генерации.
            result: Результат при успехе.
        """
        self.fail_count = fail_count
        self.error_type = error_type or MCPTimeoutError
        self.result = result or ToolExecutionResult(success=True, output="success")
        self.call_count = 0
    
    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        self.call_count += 1
        
        if self.call_count <= self.fail_count:
            # Генерируем ошибку
            if self.error_type == MCPTimeoutError:
                raise MCPTimeoutError("test_tool", 30.0)
            elif self.error_type == MCPConnectionError:
                raise MCPConnectionError("test_server")
            elif self.error_type == MCPValidationError:
                raise MCPValidationError("test_tool")
            elif self.error_type == MCPServerError:
                raise MCPServerError("test_server", "test_tool", "Server error")
            else:
                raise Exception("Unknown error")
        
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


class TestRetryDecorator:
    """Тесты для RetryDecorator."""
    
    @pytest.mark.asyncio
    async def test_execute_success_first_attempt(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Успех с первой попытки."""
        mock_executor = MockExecutor(fail_count=0)
        decorator = RetryDecorator(mock_executor, max_retries=3)
        
        result = await decorator.execute(mock_session, mock_arguments)
        
        assert result.success is True
        assert mock_executor.call_count == 1
    
    @pytest.mark.asyncio
    async def test_execute_success_after_retry(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Успех после retry."""
        mock_executor = MockExecutor(fail_count=2, error_type=MCPTimeoutError)
        decorator = RetryDecorator(
            mock_executor,
            max_retries=3,
            backoff_factor=1.0,  # Ускоряем тест
        )
        
        result = await decorator.execute(mock_session, mock_arguments)
        
        assert result.success is True
        assert mock_executor.call_count == 3  # 2 failures + 1 success
    
    @pytest.mark.asyncio
    async def test_execute_all_retries_exhausted(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Все попытки исчерпаны."""
        mock_executor = MockExecutor(fail_count=10, error_type=MCPTimeoutError)
        decorator = RetryDecorator(
            mock_executor,
            max_retries=3,
            backoff_factor=1.0,
        )
        
        result = await decorator.execute(mock_session, mock_arguments)
        
        # RetryDecorator возвращает ToolExecutionResult с ошибкой
        assert result.success is False
        assert "failed after 3 attempts" in result.error
        assert mock_executor.call_count == 3
    
    @pytest.mark.asyncio
    async def test_execute_non_retryable_error(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Non-retryable ошибка не повторяется."""
        mock_executor = MockExecutor(fail_count=10, error_type=MCPValidationError)
        decorator = RetryDecorator(mock_executor, max_retries=3)
        
        # MCPValidationError не retryable — должно подняться исключение
        with pytest.raises(MCPValidationError):
            await decorator.execute(mock_session, mock_arguments)
        
        # Только одна попытка
        assert mock_executor.call_count == 1
    
    @pytest.mark.asyncio
    async def test_execute_server_error_not_retried(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """MCPServerError не повторяется."""
        mock_executor = MockExecutor(fail_count=10, error_type=MCPServerError)
        decorator = RetryDecorator(mock_executor, max_retries=3)
        
        with pytest.raises(MCPServerError):
            await decorator.execute(mock_session, mock_arguments)
        
        assert mock_executor.call_count == 1
    
    @pytest.mark.asyncio
    async def test_execute_connection_error_is_retried(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """MCPConnectionError повторяется."""
        mock_executor = MockExecutor(fail_count=2, error_type=MCPConnectionError)
        decorator = RetryDecorator(
            mock_executor,
            max_retries=3,
            backoff_factor=1.0,
        )
        
        result = await decorator.execute(mock_session, mock_arguments)
        
        assert result.success is True
        assert mock_executor.call_count == 3
    
    @pytest.mark.asyncio
    async def test_default_max_retries_is_3(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Default max_retries равен 3."""
        mock_executor = MockExecutor()
        decorator = RetryDecorator(mock_executor)
        
        assert decorator._max_retries == 3
    
    @pytest.mark.asyncio
    async def test_default_backoff_factor_is_2(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Default backoff_factor равен 2.0."""
        mock_executor = MockExecutor()
        decorator = RetryDecorator(mock_executor)
        
        assert decorator._backoff_factor == 2.0
    
    def test_is_retryable_error_timeout(self) -> None:
        """MCPTimeoutError является retryable."""
        error = MCPTimeoutError("tool", 30.0)
        assert RetryDecorator.is_retryable_error(error) is True
    
    def test_is_retryable_error_connection(self) -> None:
        """MCPConnectionError является retryable."""
        error = MCPConnectionError("server")
        assert RetryDecorator.is_retryable_error(error) is True
    
    def test_is_retryable_error_validation(self) -> None:
        """MCPValidationError не является retryable."""
        error = MCPValidationError("tool")
        assert RetryDecorator.is_retryable_error(error) is False
    
    def test_is_retryable_error_server(self) -> None:
        """MCPServerError не является retryable."""
        error = MCPServerError("server", "tool", "error")
        assert RetryDecorator.is_retryable_error(error) is False
    
    @pytest.mark.asyncio
    async def test_execute_preserves_result_on_success(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Результат сохраняется при успехе."""
        expected_result = ToolExecutionResult(
            success=True,
            output="custom output",
            raw_output={"key": "value"},
        )
        mock_executor = MockExecutor(result=expected_result)
        decorator = RetryDecorator(mock_executor, max_retries=3)
        
        result = await decorator.execute(mock_session, mock_arguments)
        
        assert result.success == expected_result.success
        assert result.output == expected_result.output
        assert result.raw_output == expected_result.raw_output
    
    @pytest.mark.asyncio
    async def test_execute_with_custom_max_retries(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        """Кастомный max_retries корректно применяется."""
        mock_executor = MockExecutor(fail_count=10, error_type=MCPTimeoutError)
        decorator = RetryDecorator(
            mock_executor,
            max_retries=5,
            backoff_factor=1.0,
        )
        
        result = await decorator.execute(mock_session, mock_arguments)
        
        assert result.success is False
        assert "failed after 5 attempts" in result.error
        assert mock_executor.call_count == 5
