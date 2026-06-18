"""Тесты для непокрытых веток ClientRPCBridge.

Покрывают обработку ClientCapabilityMissingError и ClientRPCTimeoutError
в read_file, write_file, create_terminal, wait_terminal_exit и release_terminal.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from codelab.server.client_rpc.exceptions import (
    ClientCapabilityMissingError,
    ClientRPCError,
    ClientRPCTimeoutError,
)
from codelab.server.client_rpc.service import ClientRPCService
from codelab.server.protocol.state import SessionState
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge


@pytest.fixture
def session() -> SessionState:
    """Базовая тестовая сессия."""
    return SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
    )


@pytest.fixture
def bridge() -> ClientRPCBridge:
    """Bridge с mock ClientRPCService."""
    service = AsyncMock(spec=ClientRPCService)
    return ClientRPCBridge(client_rpc_service=service)


class TestClientRPCBridgeReadFileErrors:
    """Тесты ошибок read_file."""

    @pytest.mark.asyncio
    async def test_read_file_capability_missing_returns_none(
        self,
        bridge: ClientRPCBridge,
        session: SessionState,
    ) -> None:
        """Отсутствие capability fs.readTextFile возвращает None."""
        bridge._service.read_text_file = AsyncMock(
            side_effect=ClientCapabilityMissingError("fs.readTextFile")
        )

        result = await bridge.read_file(session, "/tmp/test.txt")

        assert result is None

    @pytest.mark.asyncio
    async def test_read_file_timeout_returns_none(
        self,
        bridge: ClientRPCBridge,
        session: SessionState,
    ) -> None:
        """Timeout при чтении файла возвращает None."""
        bridge._service.read_text_file = AsyncMock(
            side_effect=ClientRPCTimeoutError("timeout")
        )

        result = await bridge.read_file(session, "/tmp/test.txt")

        assert result is None


class TestClientRPCBridgeWriteFileErrors:
    """Тесты ошибок write_file."""

    @pytest.mark.asyncio
    async def test_write_file_capability_missing_returns_false(
        self,
        bridge: ClientRPCBridge,
        session: SessionState,
    ) -> None:
        """Отсутствие capability fs.writeTextFile возвращает False."""
        bridge._service.write_text_file = AsyncMock(
            side_effect=ClientCapabilityMissingError("fs.writeTextFile")
        )

        result = await bridge.write_file(session, "/tmp/test.txt", "data")

        assert result is False

    @pytest.mark.asyncio
    async def test_write_file_timeout_returns_false(
        self,
        bridge: ClientRPCBridge,
        session: SessionState,
    ) -> None:
        """Timeout при записи файла возвращает False."""
        bridge._service.write_text_file = AsyncMock(
            side_effect=ClientRPCTimeoutError("timeout")
        )

        result = await bridge.write_file(session, "/tmp/test.txt", "data")

        assert result is False


class TestClientRPCBridgeCreateTerminalErrors:
    """Тесты ошибок create_terminal."""

    @pytest.mark.asyncio
    async def test_create_terminal_rpc_error_returns_none(
        self,
        bridge: ClientRPCBridge,
        session: SessionState,
    ) -> None:
        """RPC-ошибка при создании терминала возвращает None."""
        bridge._service.create_terminal = AsyncMock(
            side_effect=ClientRPCError("terminal failed")
        )

        result = await bridge.create_terminal(session, command="ls")

        assert result is None


class TestClientRPCBridgeWaitTerminalExitErrors:
    """Тесты ошибок wait_terminal_exit."""

    @pytest.mark.asyncio
    async def test_wait_terminal_exit_capability_missing_returns_none(
        self,
        bridge: ClientRPCBridge,
        session: SessionState,
    ) -> None:
        """Отсутствие capability terminal возвращает None."""
        bridge._service.wait_for_exit = AsyncMock(
            side_effect=ClientCapabilityMissingError("terminal")
        )

        result = await bridge.wait_terminal_exit(session, terminal_id="term_1")

        assert result is None


class TestClientRPCBridgeReleaseTerminalErrors:
    """Тесты ошибок release_terminal."""

    @pytest.mark.asyncio
    async def test_release_terminal_capability_missing_returns_false(
        self,
        bridge: ClientRPCBridge,
        session: SessionState,
    ) -> None:
        """Отсутствие capability terminal при release возвращает False."""
        bridge._service.release_terminal = AsyncMock(
            side_effect=ClientCapabilityMissingError("terminal")
        )

        result = await bridge.release_terminal(session, terminal_id="term_1")

        assert result is False
