"""Тесты для MCP notification callbacks.

Проверяют:
- Вызов tool change callback при изменении инструментов
- Вызов resource change callback при изменении ресурсов
- Вызов prompt change callback при изменении промптов
- Вызов server status callback при изменении статуса сервера
"""

from __future__ import annotations

import pytest

from codelab.server.mcp.manager import MCPManager


@pytest.fixture
def mcp_manager() -> MCPManager:
    """Создаёт MCPManager для тестов."""
    return MCPManager(session_id="test_session")


@pytest.mark.asyncio
async def test_tool_change_callback_called_on_tools_changed(
    mcp_manager: MCPManager,
) -> None:
    """Callback вызывается когда инструменты сервера изменились."""
    callback_calls: list[int] = []

    async def test_callback() -> None:
        callback_calls.append(1)

    mcp_manager.register_tool_change_callback(test_callback)

    # Симулируем изменение инструментов
    await mcp_manager._on_tools_changed(server_id="test_server")

    assert len(callback_calls) == 1


@pytest.mark.asyncio
async def test_resource_change_callback_called_on_resources_changed(
    mcp_manager: MCPManager,
) -> None:
    """Callback вызывается когда ресурсы сервера изменились."""
    callback_calls: list[int] = []

    async def test_callback() -> None:
        callback_calls.append(1)

    mcp_manager.register_resource_change_callback(test_callback)

    # Симулируем изменение ресурсов
    await mcp_manager._on_resources_changed(server_id="test_server")

    assert len(callback_calls) == 1


@pytest.mark.asyncio
async def test_prompt_change_callback_called_on_prompts_changed(
    mcp_manager: MCPManager,
) -> None:
    """Callback вызывается когда промпты сервера изменились."""
    callback_calls: list[int] = []

    async def test_callback() -> None:
        callback_calls.append(1)

    mcp_manager.register_prompt_change_callback(test_callback)

    # Симулируем изменение промптов
    await mcp_manager._on_prompts_changed(server_id="test_server")

    assert len(callback_calls) == 1


@pytest.mark.asyncio
async def test_server_status_callback_called_on_status_changed(
    mcp_manager: MCPManager,
) -> None:
    """Callback вызывается когда статус сервера изменился."""
    callback_calls: list[int] = []

    async def test_callback() -> None:
        callback_calls.append(1)

    mcp_manager.register_server_status_callback(test_callback)

    # Симулируем изменение статуса
    await mcp_manager._notify_server_status_changed()

    assert len(callback_calls) == 1


@pytest.mark.asyncio
async def test_multiple_tool_change_callbacks(
    mcp_manager: MCPManager,
) -> None:
    """Можно зарегистрировать несколько callbacks."""
    callback1_calls: list[int] = []
    callback2_calls: list[int] = []

    async def test_callback1() -> None:
        callback1_calls.append(1)

    async def test_callback2() -> None:
        callback2_calls.append(1)

    mcp_manager.register_tool_change_callback(test_callback1)
    mcp_manager.register_tool_change_callback(test_callback2)

    await mcp_manager._on_tools_changed(server_id="test_server")

    assert len(callback1_calls) == 1
    assert len(callback2_calls) == 1


@pytest.mark.asyncio
async def test_callback_error_does_not_break_others(
    mcp_manager: MCPManager,
) -> None:
    """Ошибка в одном callback не ломает другие callbacks."""
    good_callback_calls: list[int] = []

    async def bad_callback() -> None:
        raise RuntimeError("Test error")

    async def good_callback() -> None:
        good_callback_calls.append(1)

    mcp_manager.register_tool_change_callback(bad_callback)
    mcp_manager.register_tool_change_callback(good_callback)

    # Ошибка в bad_callback не должна сломать good_callback
    await mcp_manager._on_tools_changed(server_id="test_server")

    # good_callback должен быть вызван несмотря на ошибку в bad_callback
    assert len(good_callback_calls) == 1
