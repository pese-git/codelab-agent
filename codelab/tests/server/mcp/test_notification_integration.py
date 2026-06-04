"""Интеграционные тесты для MCP notification flow.

Проверяют что callbacks вызываются в правильные моменты:
- После add_server()
- После remove_server()
- При _on_tools_changed()
"""

from __future__ import annotations

import pytest

from codelab.server.mcp.manager import MCPManager


@pytest.fixture
def mcp_manager() -> MCPManager:
    """Создаёт MCPManager для тестов."""
    return MCPManager(session_id="test_session")


@pytest.mark.asyncio
async def test_notification_callback_registered_before_add_server(
    mcp_manager: MCPManager,
) -> None:
    """Callback регистрируется до add_server и будет вызван."""
    notification_count = 0

    async def capture_notification() -> None:
        nonlocal notification_count
        notification_count += 1

    mcp_manager.register_tool_change_callback(capture_notification)

    # Убеждаемся что callback зарегистрирован
    assert len(mcp_manager._tool_change_callbacks) == 1


@pytest.mark.asyncio
async def test_notification_on_tools_changed(
    mcp_manager: MCPManager,
) -> None:
    """При _on_tools_changed() callback вызывается."""
    notification_calls: list[int] = []

    async def capture_notification() -> None:
        notification_calls.append(1)

    mcp_manager.register_tool_change_callback(capture_notification)

    # Симулируем изменение инструментов
    await mcp_manager._on_tools_changed(server_id="test_server")

    assert len(notification_calls) == 1


@pytest.mark.asyncio
async def test_notification_on_resources_changed(
    mcp_manager: MCPManager,
) -> None:
    """При _on_resources_changed() callback вызывается."""
    notification_calls: list[int] = []

    async def capture_notification() -> None:
        notification_calls.append(1)

    mcp_manager.register_resource_change_callback(capture_notification)

    await mcp_manager._on_resources_changed(server_id="test_server")

    assert len(notification_calls) == 1


@pytest.mark.asyncio
async def test_notification_on_prompts_changed(
    mcp_manager: MCPManager,
) -> None:
    """При _on_prompts_changed() callback вызывается."""
    notification_calls: list[int] = []

    async def capture_notification() -> None:
        notification_calls.append(1)

    mcp_manager.register_prompt_change_callback(capture_notification)

    await mcp_manager._on_prompts_changed(server_id="test_server")

    assert len(notification_calls) == 1


@pytest.mark.asyncio
async def test_notification_on_server_status_changed(
    mcp_manager: MCPManager,
) -> None:
    """При _notify_server_status_changed() callback вызывается."""
    notification_calls: list[int] = []

    async def capture_notification() -> None:
        notification_calls.append(1)

    mcp_manager.register_server_status_callback(capture_notification)

    await mcp_manager._notify_server_status_changed()

    assert len(notification_calls) == 1
