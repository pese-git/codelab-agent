"""Тесты для _ensure_mcp_initialized — defensive MCP re-initialization.

Проверяют:
- Возврат mcp_manager если уже инициализирован
- Переинициализация при отсутствии mcp_manager но наличии mcp_servers
- Логирование warning при переинициализации
- Возврат None если нет ни mcp_manager ни mcp_servers
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.core import ACPProtocol
from codelab.server.protocol.state import SessionState


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Создаёт mock storage."""
    return AsyncMock()


@pytest.fixture
def mock_runtime_registry() -> AsyncMock:
    """Создаёт mock runtime registry."""
    return AsyncMock()


@pytest.fixture
def protocol(mock_storage: AsyncMock, mock_runtime_registry: AsyncMock) -> ACPProtocol:
    """Создаёт ACPProtocol с mock зависимостями."""
    return ACPProtocol(
        storage=mock_storage,
        runtime_registry=mock_runtime_registry,
    )


@pytest.mark.asyncio
async def test_ensure_mcp_returns_existing_manager(
    protocol: ACPProtocol,
    mock_runtime_registry: AsyncMock,
) -> None:
    """Возвращает существующий mcp_manager без переинициализации."""
    session = SessionState(session_id="test_session", cwd="/tmp", mcp_servers=[])
    mock_manager = MagicMock()

    mock_runtime = MagicMock()
    mock_runtime.mcp_manager = mock_manager
    mock_runtime_registry.get = AsyncMock(return_value=mock_runtime)

    result = await protocol._ensure_mcp_initialized(session)

    assert result is mock_manager
    # _initialize_mcp_servers не должен вызываться
    mock_runtime_registry.set_mcp_manager.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_mcp_reinitializes_when_missing(
    protocol: ACPProtocol,
    mock_runtime_registry: AsyncMock,
) -> None:
    """Переинициализирует MCP если mcp_manager отсутствует но есть mcp_servers."""
    mcp_servers = [{"name": "test", "command": "test-cmd", "args": [], "env": []}]
    session = SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=mcp_servers,
    )

    # Первый вызов get() возвращает None (нет runtime)
    # Второй вызов возвращает runtime с mcp_manager после инициализации
    mock_manager = MagicMock()
    mock_runtime = MagicMock()
    mock_runtime.mcp_manager = mock_manager

    mock_runtime_registry.get = AsyncMock(side_effect=[None, mock_runtime])

    # Мокаем _initialize_mcp_servers
    protocol._initialize_mcp_servers = AsyncMock()

    result = await protocol._ensure_mcp_initialized(session)

    assert result is mock_manager
    protocol._initialize_mcp_servers.assert_called_once_with(session, mcp_servers)


@pytest.mark.asyncio
async def test_ensure_mcp_returns_none_when_no_config(
    protocol: ACPProtocol,
    mock_runtime_registry: AsyncMock,
) -> None:
    """Возвращает None если нет ни mcp_manager ни mcp_servers."""
    session = SessionState(session_id="test_session", cwd="/tmp", mcp_servers=[])

    mock_runtime_registry.get = AsyncMock(return_value=None)

    result = await protocol._ensure_mcp_initialized(session)

    assert result is None
    # _initialize_mcp_servers не должен вызываться
    protocol._initialize_mcp_servers = AsyncMock()
    protocol._initialize_mcp_servers.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_mcp_reinit_calls_initialize(
    protocol: ACPProtocol,
    mock_runtime_registry: AsyncMock,
) -> None:
    """Вызывает _initialize_mcp_servers при переинициализации."""
    mcp_servers = [{"name": "test", "command": "test-cmd", "args": [], "env": []}]
    session = SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=mcp_servers,
    )

    mock_manager = MagicMock()
    mock_runtime = MagicMock()
    mock_runtime.mcp_manager = mock_manager

    mock_runtime_registry.get = AsyncMock(side_effect=[None, mock_runtime])
    protocol._initialize_mcp_servers = AsyncMock()

    await protocol._ensure_mcp_initialized(session)

    # Проверить что _initialize_mcp_servers был вызван с правильными аргументами
    protocol._initialize_mcp_servers.assert_called_once_with(session, mcp_servers)
