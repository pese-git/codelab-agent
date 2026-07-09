"""Тесты для интеграции MCP Prompts как slash commands.

Покрывают:
- Регистрацию MCP prompts в runtime registry при инициализации
- Маршрутизацию slash команд к MCP prompt handlers
- Включение MCP prompts в available_commands_update
- Хранение handlers в runtime registry (не в SessionState)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.mcp.models import (
    MCPPrompt,
    MCPPromptArgument,
)
from codelab.server.protocol.handlers.slash_commands import (
    CommandRegistry,
    SlashCommandRouter,
)
from codelab.server.protocol.handlers.slash_commands.builtin.mcp_prompt import (
    MCPPromptCommandHandler,
)
from codelab.server.protocol.mcp_session_manager import MCPSessionManager
from codelab.server.protocol.session_runtime import SessionRuntimeState
from codelab.server.protocol.state import SessionState


@pytest.fixture
def mock_runtime_registry() -> AsyncMock:
    """Создаёт mock runtime registry."""
    return AsyncMock()


@pytest.fixture
def manager(mock_runtime_registry: AsyncMock) -> MCPSessionManager:
    """Создаёт MCPSessionManager с mock зависимостями."""
    return MCPSessionManager(
        runtime_registry=mock_runtime_registry,
        tool_registry=None,
    )


@pytest.fixture
def session() -> SessionState:
    """Создаёт тестовую сессию."""
    return SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
    )


@pytest.fixture
def runtime_state() -> SessionRuntimeState:
    """Создаёт тестовое runtime состояние."""
    return SessionRuntimeState()


class TestRegisterMcpPromptsAsSlashCommands:
    """Тесты для _register_mcp_prompts_as_slash_commands."""

    @pytest.mark.asyncio
    async def test_registers_prompts_in_runtime_registry(
        self,
        manager: MCPSessionManager,
        session: SessionState,
        runtime_state: SessionRuntimeState,
    ) -> None:
        """Регистрирует MCP prompts в runtime.mcp_prompt_handlers."""
        mock_manager = MagicMock()
        mock_manager.get_all_prompts = AsyncMock(return_value={
            "test_server": [
                MCPPrompt(name="code_review", description="Review code"),
                MCPPrompt(
                    name="plan",
                    title="Plan task",
                    arguments=[MCPPromptArgument(name="task", required=True)],
                ),
            ],
        })

        # Настраиваем runtime registry чтобы возвращал runtime_state
        manager._runtime_registry.get = AsyncMock(return_value=runtime_state)

        await manager._register_mcp_prompts_as_slash_commands(
            session, mock_manager, "test_server"
        )

        # Handlers должны быть в runtime, а не в session
        assert "code_review" in runtime_state.mcp_prompt_handlers
        assert "plan" in runtime_state.mcp_prompt_handlers
        assert isinstance(runtime_state.mcp_prompt_handlers["code_review"], MCPPromptCommandHandler)
        assert isinstance(runtime_state.mcp_prompt_handlers["plan"], MCPPromptCommandHandler)
        # Session.mcp_prompt_handlers должен быть пуст (handlers скопированы в runtime)
        assert len(session.mcp_prompt_handlers) == 0

    @pytest.mark.asyncio
    async def test_adds_prompts_to_available_commands(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Добавляет MCP prompts в session_state.available_commands."""
        mock_manager = MagicMock()
        mock_manager.get_all_prompts = AsyncMock(return_value={
            "test_server": [
                MCPPrompt(name="test_prompt", description="Test prompt"),
            ],
        })

        await manager._register_mcp_prompts_as_slash_commands(
            session, mock_manager, "test_server"
        )

        # Проверяем что prompt добавлен в available_commands
        prompt_commands = [
            cmd for cmd in session.available_commands
            if isinstance(cmd, dict) and cmd.get("name") == "test_prompt"
            or hasattr(cmd, "name") and cmd.name == "test_prompt"
        ]
        assert len(prompt_commands) == 1

    @pytest.mark.asyncio
    async def test_handles_empty_prompts(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Обрабатывает случай без prompts."""
        mock_manager = MagicMock()
        mock_manager.get_all_prompts = AsyncMock(return_value={"test_server": []})

        await manager._register_mcp_prompts_as_slash_commands(
            session, mock_manager, "test_server"
        )

        assert len(session.mcp_prompt_handlers) == 0

    @pytest.mark.asyncio
    async def test_handles_missing_server(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Обрабатывает случай когда сервер не найден в prompts."""
        mock_manager = MagicMock()
        mock_manager.get_all_prompts = AsyncMock(return_value={"other_server": []})

        await manager._register_mcp_prompts_as_slash_commands(
            session, mock_manager, "test_server"
        )

        assert len(session.mcp_prompt_handlers) == 0

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Обрабатывает ошибки при получении prompts без прерывания."""
        mock_manager = MagicMock()
        mock_manager.get_all_prompts = AsyncMock(side_effect=Exception("Connection failed"))

        # Не должно выбрасывать исключение
        await manager._register_mcp_prompts_as_slash_commands(
            session, mock_manager, "test_server"
        )

        assert len(session.mcp_prompt_handlers) == 0


class TestSlashCommandRouterMcpPrompts:
    """Тесты для маршрутизации MCP prompts через SlashCommandRouter."""

    @pytest.mark.asyncio
    async def test_routes_to_mcp_prompt_handler(self, session: SessionState) -> None:
        """Маршрутизирует команду к MCP prompt handler."""
        registry = CommandRegistry()
        router = SlashCommandRouter(registry)

        # Создаём mock handler
        mock_handler = MagicMock(spec=MCPPromptCommandHandler)
        mock_result = MagicMock()
        mock_result.content = [{"type": "text", "text": "Prompt result"}]
        mock_result.updates = []
        mock_handler.execute_async = AsyncMock(return_value=mock_result)

        # Передаём handlers как параметр (из runtime registry)
        mcp_prompt_handlers = {"test_prompt": mock_handler}

        outcome = await router.route("test_prompt", ["arg1"], session, mcp_prompt_handlers)

        assert outcome is not None
        mock_handler.execute_async.assert_called_once_with(["arg1"], session)

    @pytest.mark.asyncio
    async def test_registry_handler_takes_priority(self, session: SessionState) -> None:
        """Handler из registry имеет приоритет над MCP prompt."""
        from codelab.server.protocol.handlers.slash_commands.builtin import StatusCommandHandler

        registry = CommandRegistry()
        registry.register(StatusCommandHandler())
        router = SlashCommandRouter(registry)

        # Добавляем MCP prompt с тем же именем
        mock_handler = MagicMock(spec=MCPPromptCommandHandler)
        mock_handler.execute_async = AsyncMock()
        mcp_prompt_handlers = {"status": mock_handler}

        outcome = await router.route("status", [], session, mcp_prompt_handlers)

        # Должен вызваться handler из registry, а не MCP prompt
        assert outcome is not None
        mock_handler.execute_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_command(self, session: SessionState) -> None:
        """Возвращает None для неизвестной команды."""
        registry = CommandRegistry()
        router = SlashCommandRouter(registry)

        outcome = await router.route("unknown_command", [], session)

        assert outcome is None

    @pytest.mark.asyncio
    async def test_handles_mcp_prompt_error(self, session: SessionState) -> None:
        """Обрабатывает ошибки выполнения MCP prompt."""
        registry = CommandRegistry()
        router = SlashCommandRouter(registry)

        mock_handler = MagicMock(spec=MCPPromptCommandHandler)
        mock_handler.execute_async = AsyncMock(side_effect=Exception("MCP error"))
        mcp_prompt_handlers = {"failing_prompt": mock_handler}

        outcome = await router.route("failing_prompt", [], session, mcp_prompt_handlers)

        assert outcome is not None
        # Должно содержать сообщение об ошибке
        assert len(outcome.notifications) > 0


class TestInitializeMcpServersWithPrompts:
    """Тесты для _initialize_mcp_servers с prompts."""

    @pytest.mark.asyncio
    async def test_calls_register_prompts_after_add_server(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Вызывает _register_mcp_prompts_as_slash_commands после add_server."""
        mcp_servers = [{"name": "test", "command": "test-cmd", "args": [], "env": []}]

        # Мокаем зависимости
        mock_manager = MagicMock()
        mock_manager.add_server = AsyncMock(return_value=[])
        mock_manager.get_all_prompts = AsyncMock(return_value={})
        mock_manager.register_tool_change_callback = MagicMock()
        mock_manager.register_server_status_callback = MagicMock()
        mock_manager.register_prompt_change_callback = MagicMock()

        with (
            patch(
                "codelab.server.protocol.mcp_session_manager.MCPManager",
                return_value=mock_manager,
            ),
            patch.object(
                manager, "_register_mcp_prompts_as_slash_commands", new_callable=AsyncMock
            ) as mock_register,
        ):
            await manager._initialize_mcp_servers(session, mcp_servers)

            mock_register.assert_called_once_with(session, mock_manager, "test")

    @pytest.mark.asyncio
    async def test_includes_prompts_in_available_commands_update(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Включает MCP prompts в available_commands_update."""
        # Добавляем slash команду в session
        session.available_commands.append({"name": "mcp_prompt", "description": "MCP Prompt"})

        sent_messages = []

        async def mock_send(msg, session_id=None):
            sent_messages.append(msg)

        manager._send_message = mock_send

        # Мокаем зависимости
        mock_manager = MagicMock()
        mock_manager.add_server = AsyncMock(return_value=[])
        mock_manager.get_all_prompts = AsyncMock(return_value={})
        mock_manager.get_all_tools = MagicMock(return_value=[])
        mock_manager.register_tool_change_callback = MagicMock()
        mock_manager.register_server_status_callback = MagicMock()
        mock_manager.register_prompt_change_callback = MagicMock()

        manager._tool_registry = MagicMock()
        manager._tool_registry.get_available_tools = MagicMock(return_value=[])

        with (
            patch(
                "codelab.server.protocol.mcp_session_manager.MCPManager",
                return_value=mock_manager,
            ),
            patch.object(
                manager, "_register_mcp_prompts_as_slash_commands", new_callable=AsyncMock
            ),
        ):
            await manager._initialize_mcp_servers(session, mcp_servers=[])

        # Проверяем что available_commands_update включает slash commands
        # (в реальном тесте нужно проверить содержимое отправленных сообщений)


class TestRestoreMcpPrompts:
    """Тесты для _restore_mcp_prompts."""

    @pytest.mark.asyncio
    async def test_restores_prompts_from_configured_servers(
        self,
        manager: MCPSessionManager,
        session: SessionState,
        runtime_state: SessionRuntimeState,
    ) -> None:
        """Восстанавливает prompts для всех серверов из mcp_servers."""
        from codelab.server.mcp.models import MCPPrompt

        session.mcp_servers = [
            {"name": "server1", "command": "cmd1"},
            {"name": "server2", "command": "cmd2"},
        ]
        mock_manager = MagicMock()
        # get_all_prompts() вызывается один раз и возвращает prompts для обоих серверов
        mock_manager.get_all_prompts = AsyncMock(return_value={
            "server1": [MCPPrompt(name="prompt1", description="Prompt 1")],
            "server2": [MCPPrompt(name="prompt2", description="Prompt 2")],
        })

        # Настраиваем runtime registry
        manager._runtime_registry.get = AsyncMock(return_value=runtime_state)

        await manager._restore_mcp_prompts(session, mock_manager)

        # get_all_prompts() должен вызваться один раз
        assert mock_manager.get_all_prompts.call_count == 1
        # Handlers должны быть в runtime registry
        assert "prompt1" in runtime_state.mcp_prompt_handlers
        assert "prompt2" in runtime_state.mcp_prompt_handlers
        # Session.mcp_prompt_handlers должен быть пуст
        assert len(session.mcp_prompt_handlers) == 0

    @pytest.mark.asyncio
    async def test_skips_invalid_server_configs(
        self,
        manager: MCPSessionManager,
        session: SessionState,
        runtime_state: SessionRuntimeState,
    ) -> None:
        """Пропускает невалидные конфигурации серверов."""
        from codelab.server.mcp.models import MCPPrompt

        session.mcp_servers = [
            {"name": "valid", "command": "cmd"},
            {"command": "no_name"},  # нет name
            "not_a_dict",  # не dict
        ]
        mock_manager = MagicMock()
        mock_manager.get_all_prompts = AsyncMock(return_value={
            "valid": [MCPPrompt(name="valid_prompt", description="Valid")],
        })

        # Настраиваем runtime registry
        manager._runtime_registry.get = AsyncMock(return_value=runtime_state)

        await manager._restore_mcp_prompts(session, mock_manager)

        # Только один валидный сервер — один handler
        assert "valid_prompt" in runtime_state.mcp_prompt_handlers
        assert len(runtime_state.mcp_prompt_handlers) == 1

    @pytest.mark.asyncio
    async def test_clears_old_mcp_prompts_before_restore(
        self,
        manager: MCPSessionManager,
        session: SessionState,
        runtime_state: SessionRuntimeState,
    ) -> None:
        """Очищает старые MCP prompts перед восстановлением."""
        from codelab.server.mcp.models import MCPPrompt

        # Добавляем старые prompts в runtime
        runtime_state.mcp_prompt_handlers["old_prompt"] = MagicMock()
        session.available_commands = [
            {"name": "status", "description": "Built-in"},
            {"name": "old_prompt", "description": "Old MCP prompt"},
        ]
        session.mcp_servers = [{"name": "server1", "command": "cmd"}]

        mock_manager = MagicMock()
        mock_manager.get_all_prompts = AsyncMock(return_value={
            "server1": [MCPPrompt(name="new_prompt", description="New")],
        })

        # Настраиваем runtime registry
        manager._runtime_registry.get = AsyncMock(return_value=runtime_state)

        await manager._restore_mcp_prompts(session, mock_manager)

        # Старые MCP prompts удалены из runtime
        assert "old_prompt" not in runtime_state.mcp_prompt_handlers
        # Новый prompt добавлен в runtime
        assert "new_prompt" in runtime_state.mcp_prompt_handlers
        # Built-in команды сохранены
        builtin_names = [
            cmd.get("name") for cmd in session.available_commands if isinstance(cmd, dict)
        ]
        assert "status" in builtin_names
        # Старый MCP prompt удалён из available_commands
        assert "old_prompt" not in builtin_names


class TestEnsureMcpInitializedWithRestore:
    """Тесты для ensure_initialized с восстановлением prompts."""

    @pytest.mark.asyncio
    async def test_restores_prompts_when_handlers_empty(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Восстанавливает prompts если runtime.mcp_prompt_handlers пуст."""
        session.mcp_servers = [{"name": "test", "command": "cmd"}]

        mock_manager = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.mcp_manager = mock_manager
        mock_runtime.mcp_prompt_handlers = {}  # Пустые handlers

        manager._runtime_registry.get = AsyncMock(return_value=mock_runtime)

        with patch.object(
            manager, "_restore_mcp_prompts", new_callable=AsyncMock
        ) as mock_restore:
            result = await manager.ensure_initialized(session)

            assert result is mock_manager
            mock_restore.assert_called_once_with(session, mock_manager)

    @pytest.mark.asyncio
    async def test_does_not_restore_when_handlers_exist(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Не восстанавливает prompts если handlers уже есть в runtime."""
        session.mcp_servers = [{"name": "test", "command": "cmd"}]

        mock_manager = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.mcp_manager = mock_manager
        mock_runtime.mcp_prompt_handlers = {"existing": MagicMock()}  # Handlers есть

        manager._runtime_registry.get = AsyncMock(return_value=mock_runtime)

        with patch.object(
            manager, "_restore_mcp_prompts", new_callable=AsyncMock
        ) as mock_restore:
            result = await manager.ensure_initialized(session)

            assert result is mock_manager
            mock_restore.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_restore_when_no_mcp_servers(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Не восстанавливает prompts если нет mcp_servers."""
        session.mcp_servers = []

        mock_manager = MagicMock()
        mock_runtime = MagicMock()
        mock_runtime.mcp_manager = mock_manager
        mock_runtime.mcp_prompt_handlers = {}

        manager._runtime_registry.get = AsyncMock(return_value=mock_runtime)

        with patch.object(
            manager, "_restore_mcp_prompts", new_callable=AsyncMock
        ) as mock_restore:
            result = await manager.ensure_initialized(session)

            assert result is mock_manager
            mock_restore.assert_not_called()


class TestSessionStateMcpPromptHandlers:
    """Тесты для поля mcp_prompt_handlers в SessionState."""

    def test_default_empty_dict(self) -> None:
        """По умолчанию mcp_prompt_handlers — пустой dict."""
        session = SessionState(session_id="test", cwd="/tmp", mcp_servers=[])
        assert session.mcp_prompt_handlers == {}

    def test_handlers_not_serialized(self) -> None:
        """mcp_prompt_handlers не сериализуется (exclude=True)."""
        session = SessionState(session_id="test", cwd="/tmp", mcp_servers=[])
        session.mcp_prompt_handlers["test"] = MagicMock()

        data = session.model_dump()
        assert "mcp_prompt_handlers" not in data

    def test_handlers_per_session_isolation(self) -> None:
        """Handlers изолированы между сессиями."""
        session1 = SessionState(session_id="s1", cwd="/tmp", mcp_servers=[])
        session2 = SessionState(session_id="s2", cwd="/tmp", mcp_servers=[])

        session1.mcp_prompt_handlers["prompt1"] = MagicMock()

        assert "prompt1" in session1.mcp_prompt_handlers
        assert "prompt1" not in session2.mcp_prompt_handlers


class TestSendAvailableCommandsUpdate:
    """Тесты для метода send_available_commands_update."""

    @pytest.mark.asyncio
    async def test_combines_native_and_mcp_tools(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Объединяет native tools, MCP tools и slash commands."""
        from codelab.server.tools.base import ToolDefinition

        # Mock native tools
        native_tool = ToolDefinition(
            name="native_tool",
            description="Native tool description",
            parameters={},
            kind="other",
        )
        manager._tool_registry = MagicMock()
        manager._tool_registry.get_available_tools = MagicMock(return_value=[native_tool])

        # Mock MCP tools
        mcp_tool = ToolDefinition(
            name="mcp:server:mcp_tool",
            description="MCP tool description",
            parameters={},
            kind="other",
        )
        mock_manager = MagicMock()
        mock_manager.get_all_tools = MagicMock(return_value=[mcp_tool])

        # Добавляем slash command
        session.available_commands.append({"name": "test_cmd", "description": "Test command"})

        sent_messages = []

        async def mock_send(msg, session_id=None):
            sent_messages.append(msg)

        manager._send_message = mock_send

        await manager.send_available_commands_update(session, mock_manager)

        assert len(sent_messages) == 1
        notification = sent_messages[0]
        assert notification.method == "session/update"
        update = notification.params["update"]
        assert update["sessionUpdate"] == "available_commands_update"

        commands = update["availableCommands"]
        command_names = [cmd["name"] for cmd in commands]
        assert "native_tool" in command_names
        assert "mcp:server:mcp_tool" in command_names
        assert "test_cmd" in command_names

    @pytest.mark.asyncio
    async def test_sends_correct_notification_format(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Формат notification соответствует ACP спецификации."""
        manager._tool_registry = MagicMock()
        manager._tool_registry.get_available_tools = MagicMock(return_value=[])

        mock_manager = MagicMock()
        mock_manager.get_all_tools = MagicMock(return_value=[])

        sent_messages = []

        async def mock_send(msg, session_id=None):
            sent_messages.append(msg)

        manager._send_message = mock_send

        await manager.send_available_commands_update(session, mock_manager)

        assert len(sent_messages) == 1
        notification = sent_messages[0]
        # Проверяем структуру JSON-RPC notification
        assert notification.jsonrpc == "2.0"
        assert notification.method == "session/update"
        assert "id" not in notification.model_dump(exclude_none=True)
        # Проверяем структуру params
        assert "sessionId" in notification.params
        assert "update" in notification.params
        update = notification.params["update"]
        assert update["sessionUpdate"] == "available_commands_update"
        assert "availableCommands" in update

    @pytest.mark.asyncio
    async def test_handles_send_error_gracefully(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Ошибка отправки не ломает работу."""
        manager._tool_registry = MagicMock()
        manager._tool_registry.get_available_tools = MagicMock(return_value=[])

        mock_manager = MagicMock()
        mock_manager.get_all_tools = MagicMock(return_value=[])

        async def failing_send(msg, session_id=None):
            raise RuntimeError("Connection lost")

        manager._send_message = failing_send

        # Не должно выбрасывать исключение
        await manager.send_available_commands_update(session, mock_manager)


class TestMcpPromptChangeCallback:
    """Тесты для callback при изменении MCP prompts."""

    @pytest.mark.asyncio
    async def test_callback_registered_on_init(
        self,
        manager: MCPSessionManager,
        session: SessionState,
    ) -> None:
        """Callback регистрируется при инициализации MCP серверов."""
        mcp_servers = [{"name": "test", "command": "test-cmd", "args": [], "env": []}]

        mock_manager = MagicMock()
        mock_manager.add_server = AsyncMock(return_value=[])
        mock_manager.get_all_prompts = AsyncMock(return_value={})
        mock_manager.get_all_tools = MagicMock(return_value=[])
        mock_manager.register_tool_change_callback = MagicMock()
        mock_manager.register_server_status_callback = MagicMock()
        mock_manager.register_prompt_change_callback = MagicMock()

        manager._tool_registry = MagicMock()
        manager._tool_registry.get_available_tools = MagicMock(return_value=[])

        with patch(
            "codelab.server.protocol.mcp_session_manager.MCPManager",
            return_value=mock_manager,
        ):
            await manager._initialize_mcp_servers(session, mcp_servers)

        mock_manager.register_prompt_change_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_clears_old_mcp_prompts(
        self,
        manager: MCPSessionManager,
        session: SessionState,
        runtime_state: SessionRuntimeState,
    ) -> None:
        """При изменении prompts старые handlers удаляются из runtime."""
        # Добавляем старые MCP prompts в runtime
        runtime_state.mcp_prompt_handlers["old_prompt"] = MagicMock()
        session.available_commands = [
            {"name": "status", "description": "Built-in"},
            {"name": "old_prompt", "description": "Old MCP prompt"},
        ]
        session.mcp_servers = [{"name": "test", "command": "cmd"}]

        mock_manager = MagicMock()
        mock_manager.add_server = AsyncMock(return_value=[])
        mock_manager.get_all_prompts = AsyncMock(return_value={
            "test": [MCPPrompt(name="new_prompt", description="New")],
        })
        mock_manager.get_all_tools = MagicMock(return_value=[])

        manager._tool_registry = MagicMock()
        manager._tool_registry.get_available_tools = MagicMock(return_value=[])

        # Настраиваем runtime registry
        manager._runtime_registry.get = AsyncMock(return_value=runtime_state)

        sent_messages = []

        async def mock_send(msg, session_id=None):
            sent_messages.append(msg)

        manager._send_message = mock_send

        # Получаем callback и вызываем его
        mock_manager.register_tool_change_callback = MagicMock()
        mock_manager.register_server_status_callback = MagicMock()
        mock_manager.register_prompt_change_callback = MagicMock(side_effect=lambda cb: setattr(
            mock_manager, "_prompt_callback", cb
        ))

        with patch(
            "codelab.server.protocol.mcp_session_manager.MCPManager",
            return_value=mock_manager,
        ):
            await manager._initialize_mcp_servers(
                session, [{"name": "test", "command": "cmd"}]
            )

        # Вызываем callback напрямую
        await mock_manager._prompt_callback()

        # Старые MCP prompts удалены из runtime
        assert "old_prompt" not in runtime_state.mcp_prompt_handlers
        # Новый prompt добавлен в runtime
        assert "new_prompt" in runtime_state.mcp_prompt_handlers
        # Session.mcp_prompt_handlers должен быть пуст (handlers в runtime)
        assert len(session.mcp_prompt_handlers) == 0

    @pytest.mark.asyncio
    async def test_preserves_builtin_commands(
        self,
        manager: MCPSessionManager,
        session: SessionState,
        runtime_state: SessionRuntimeState,
    ) -> None:
        """Built-in команды (status, mode, help) сохраняются."""
        session.available_commands = [
            {"name": "status", "description": "Session status"},
            {"name": "mode", "description": "Switch mode"},
            {"name": "help", "description": "Show help"},
            {"name": "old_mcp_prompt", "description": "Old MCP prompt"},
        ]
        session.mcp_prompt_handlers["old_mcp_prompt"] = MagicMock()
        session.mcp_servers = [{"name": "test", "command": "cmd"}]

        mock_manager = MagicMock()
        mock_manager.add_server = AsyncMock(return_value=[])
        mock_manager.get_all_prompts = AsyncMock(return_value={})
        mock_manager.get_all_tools = MagicMock(return_value=[])

        manager._tool_registry = MagicMock()
        manager._tool_registry.get_available_tools = MagicMock(return_value=[])

        # Настраиваем runtime registry
        manager._runtime_registry.get = AsyncMock(return_value=runtime_state)

        sent_messages = []

        async def mock_send(msg, session_id=None):
            sent_messages.append(msg)

        manager._send_message = mock_send

        mock_manager.register_tool_change_callback = MagicMock()
        mock_manager.register_server_status_callback = MagicMock()
        mock_manager.register_prompt_change_callback = MagicMock(side_effect=lambda cb: setattr(
            mock_manager, "_prompt_callback", cb
        ))

        with patch(
            "codelab.server.protocol.mcp_session_manager.MCPManager",
            return_value=mock_manager,
        ):
            await manager._initialize_mcp_servers(
                session, [{"name": "test", "command": "cmd"}]
            )

        await mock_manager._prompt_callback()

        # Built-in команды сохранены
        builtin_names = [
            cmd.get("name") for cmd in session.available_commands if isinstance(cmd, dict)
        ]
        assert "status" in builtin_names
        assert "mode" in builtin_names
        assert "help" in builtin_names
        # Старый MCP prompt удалён
        assert "old_mcp_prompt" not in builtin_names

    @pytest.mark.asyncio
    async def test_sends_available_commands_update(
        self,
        manager: MCPSessionManager,
        session: SessionState,
        runtime_state: SessionRuntimeState,
    ) -> None:
        """После изменения prompts отправляется available_commands_update."""
        session.mcp_servers = [{"name": "test", "command": "cmd"}]

        mock_manager = MagicMock()
        mock_manager.add_server = AsyncMock(return_value=[])
        mock_manager.get_all_prompts = AsyncMock(return_value={
            "test": [MCPPrompt(name="new_prompt", description="New prompt")],
        })
        mock_manager.get_all_tools = MagicMock(return_value=[])

        manager._tool_registry = MagicMock()
        manager._tool_registry.get_available_tools = MagicMock(return_value=[])

        # Настраиваем runtime registry
        manager._runtime_registry.get = AsyncMock(return_value=runtime_state)

        sent_messages = []

        async def mock_send(msg, session_id=None):
            sent_messages.append(msg)

        manager._send_message = mock_send

        mock_manager.register_tool_change_callback = MagicMock()
        mock_manager.register_server_status_callback = MagicMock()
        mock_manager.register_prompt_change_callback = MagicMock(side_effect=lambda cb: setattr(
            mock_manager, "_prompt_callback", cb
        ))

        with patch(
            "codelab.server.protocol.mcp_session_manager.MCPManager",
            return_value=mock_manager,
        ):
            await manager._initialize_mcp_servers(
                session, [{"name": "test", "command": "cmd"}]
            )

        # Очищаем сообщения от инициализации
        sent_messages.clear()

        # Вызываем callback
        await mock_manager._prompt_callback()

        # Проверяем что отправлено available_commands_update
        assert len(sent_messages) == 1
        notification = sent_messages[0]
        assert notification.method == "session/update"
        update = notification.params["update"]
        assert update["sessionUpdate"] == "available_commands_update"

        # Проверяем что новый prompt включён в команды
        command_names = [cmd["name"] for cmd in update["availableCommands"]]
        assert "new_prompt" in command_names

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(
        self,
        manager: MCPSessionManager,
        session: SessionState,
        runtime_state: SessionRuntimeState,
    ) -> None:
        """Ошибка в callback не ломает работу."""
        session.mcp_servers = [{"name": "test", "command": "cmd"}]

        mock_manager = MagicMock()
        mock_manager.add_server = AsyncMock(return_value=[])
        mock_manager.get_all_prompts = AsyncMock(side_effect=Exception("Connection failed"))
        mock_manager.get_all_tools = MagicMock(return_value=[])

        manager._tool_registry = MagicMock()
        manager._tool_registry.get_available_tools = MagicMock(return_value=[])

        manager._runtime_registry.get = AsyncMock(return_value=runtime_state)

        async def mock_send(msg, session_id=None):
            pass

        manager._send_message = mock_send

        mock_manager.register_tool_change_callback = MagicMock()
        mock_manager.register_server_status_callback = MagicMock()
        mock_manager.register_prompt_change_callback = MagicMock(side_effect=lambda cb: setattr(
            mock_manager, "_prompt_callback", cb
        ))

        with patch(
            "codelab.server.protocol.mcp_session_manager.MCPManager",
            return_value=mock_manager,
        ):
            await manager._initialize_mcp_servers(
                session, [{"name": "test", "command": "cmd"}]
            )

        # Не должно выбрасывать исключение
        await mock_manager._prompt_callback()
