"""Тесты для непокрытых веток TerminalToolExecutor.

Покрывают диспетчеризацию операций в execute, ошибки create/release
и обработку сигнала после wait_for_exit.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.tools.executors.terminal_executor import TerminalToolExecutor


@pytest.fixture
def session() -> SessionState:
    """Тестовая сессия."""
    return SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
        config_values={},
    )


@pytest.fixture
def executor() -> TerminalToolExecutor:
    """Executor с mock bridge."""
    bridge = MagicMock()
    checker = MagicMock()
    return TerminalToolExecutor(bridge, checker)


class TestTerminalExecutorDispatch:
    """Тесты dispatch в execute."""

    @pytest.mark.asyncio
    async def test_execute_create(
        self, executor: TerminalToolExecutor, session: SessionState
    ) -> None:
        """execute dispatch'ит operation=create в execute_create."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_1")

        result = await executor.execute(
            session,
            {"operation": "create", "command": "ls"},
        )

        assert result.success is True
        executor._bridge.create_terminal.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_wait_for_exit(
        self, executor: TerminalToolExecutor, session: SessionState
    ) -> None:
        """execute dispatch'ит operation=wait_for_exit в execute_wait_for_exit."""
        executor._bridge.terminal_output = AsyncMock(return_value={
            "output": "done",
            "truncated": False,
            "is_complete": True,
            "exit_code": 0,
            "signal": None,
        })

        result = await executor.execute(
            session,
            {"operation": "wait_for_exit", "terminal_id": "term_1"},
        )

        assert result.success is True
        executor._bridge.terminal_output.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_release(
        self, executor: TerminalToolExecutor, session: SessionState
    ) -> None:
        """execute dispatch'ит operation=release в execute_release."""
        executor._bridge.release_terminal = AsyncMock(return_value=True)

        result = await executor.execute(
            session,
            {"operation": "release", "terminal_id": "term_1"},
        )

        assert result.success is True
        executor._bridge.release_terminal.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_unknown_operation(
        self, executor: TerminalToolExecutor, session: SessionState
    ) -> None:
        """Неизвестная operation возвращает ошибку."""
        result = await executor.execute(
            session,
            {"operation": "unknown"},
        )

        assert result.success is False
        assert "Неизвестная операция" in result.error


class TestTerminalExecutorCreateErrors:
    """Тесты ошибок создания терминала."""

    @pytest.mark.asyncio
    async def test_create_terminal_returns_none(
        self, executor: TerminalToolExecutor, session: SessionState
    ) -> None:
        """Если bridge.create_terminal вернул None, возвращается ошибка."""
        executor._bridge.create_terminal = AsyncMock(return_value=None)

        result = await executor.execute_create(session, command="ls")

        assert result.success is False
        assert "ls" in result.error


class TestTerminalExecutorWaitForExitSignal:
    """Тесты обработки сигнала после wait_for_exit."""

    @pytest.mark.asyncio
    async def test_wait_for_exit_signal_after_wait(
        self,
        executor: TerminalToolExecutor,
        session: SessionState,
    ) -> None:
        """Сигнал после wait_for_exit корректно отображается в результате."""
        executor._bridge.terminal_output = AsyncMock(side_effect=[
            {
                "output": "partial",
                "truncated": False,
                "is_complete": False,
                "exit_code": None,
                "signal": None,
            },
            {
                "output": "killed",
                "truncated": False,
                "is_complete": True,
                "exit_code": None,
                "signal": "SIGTERM",
            },
        ])
        executor._bridge.wait_terminal_exit = AsyncMock(return_value={
            "exit_code": None,
            "signal": "SIGTERM",
        })

        result = await executor.execute_wait_for_exit(session, terminal_id="term_1")

        assert result.success is False
        assert result.metadata["signal"] == "SIGTERM"
        assert any(
            "signal SIGTERM" in item["text"]
            for item in result.content
            if item["type"] == "text"
        )


class TestTerminalExecutorReleaseErrors:
    """Тесты ошибок освобождения терминала."""

    @pytest.mark.asyncio
    async def test_release_terminal_exception(
        self,
        executor: TerminalToolExecutor,
        session: SessionState,
    ) -> None:
        """Исключение в release_terminal обрабатывается и возвращает ошибку."""
        executor._bridge.release_terminal = AsyncMock(side_effect=RuntimeError("boom"))

        result = await executor.execute_release(session, terminal_id="term_1")

        assert result.success is False
        assert "boom" in result.error
