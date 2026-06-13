"""Тесты для инфраструктуры slash commands.

Проверяет CommandRegistry, SlashCommandRouter и CommandHandler.
"""

import pytest

from codelab.server.models import AvailableCommand, AvailableCommandInput
from codelab.server.protocol.handlers.slash_commands import (
    CommandHandler,
    CommandRegistry,
    CommandResult,
    SlashCommandRouter,
)
from codelab.server.protocol.handlers.slash_commands.builtin import (
    HelpCommandHandler,
    ModeCommandHandler,
    StatusCommandHandler,
)
from codelab.server.protocol.state import SessionState


@pytest.fixture
def session() -> SessionState:
    """Создает тестовую сессию."""
    return SessionState(
        session_id="test_session_123",
        cwd="/tmp/test",
        mcp_servers=[],
        title="Test Session",
        config_values={"mode": "code"},
    )


@pytest.fixture
def registry() -> CommandRegistry:
    """Создает пустой реестр команд."""
    return CommandRegistry()


class DummyHandler(CommandHandler):
    """Тестовый handler для проверки регистрации."""

    def __init__(self, name: str = "dummy", description: str = "Dummy command") -> None:
        self._name = name
        self._description = description

    def execute(self, args: list[str], session: SessionState) -> CommandResult:
        return CommandResult(
            content=[{"type": "text", "text": f"Dummy executed with args: {args}"}]
        )

    def get_definition(self) -> AvailableCommand:
        return AvailableCommand(name=self._name, description=self._description)


class TestCommandRegistry:
    """Тесты для CommandRegistry."""

    def test_register_handler(self, registry: CommandRegistry) -> None:
        """Регистрация handler'а добавляет его в реестр."""
        handler = DummyHandler("test", "Test command")
        registry.register(handler)

        assert registry.has_handler("test")
        assert registry.get_handler("test") is handler

    def test_register_duplicate_raises(self, registry: CommandRegistry) -> None:
        """Повторная регистрация команды вызывает ошибку."""
        registry.register(DummyHandler("test"))

        with pytest.raises(ValueError, match="already registered"):
            registry.register(DummyHandler("test"))

    def test_unregister_handler(self, registry: CommandRegistry) -> None:
        """Удаление handler'а из реестра."""
        registry.register(DummyHandler("test"))
        assert registry.has_handler("test")

        result = registry.unregister("test")
        assert result is True
        assert not registry.has_handler("test")

    def test_unregister_nonexistent(self, registry: CommandRegistry) -> None:
        """Удаление несуществующей команды возвращает False."""
        result = registry.unregister("nonexistent")
        assert result is False

    def test_get_commands(self, registry: CommandRegistry) -> None:
        """Получение списка всех команд."""
        registry.register(DummyHandler("cmd1", "Command 1"))
        registry.register(DummyHandler("cmd2", "Command 2"))

        commands = registry.get_commands()
        assert len(commands) == 2
        names = {c.name for c in commands}
        assert names == {"cmd1", "cmd2"}

    def test_add_dynamic_command(self, registry: CommandRegistry) -> None:
        """Добавление динамической команды без handler."""
        cmd = AvailableCommand(
            name="dynamic",
            description="Dynamic command",
            input=AvailableCommandInput(hint="some input"),
        )
        registry.add_dynamic_command(cmd)

        commands = registry.get_commands()
        assert len(commands) == 1
        assert commands[0].name == "dynamic"
        # Динамическая команда не имеет handler
        assert not registry.has_handler("dynamic")

    def test_get_commands_as_dicts(self, registry: CommandRegistry) -> None:
        """Получение команд в формате dict для JSON-RPC."""
        registry.register(DummyHandler("cmd1", "Command 1"))

        dicts = registry.get_commands_as_dicts()
        assert len(dicts) == 1
        assert dicts[0] == {"name": "cmd1", "description": "Command 1"}

    def test_registered_commands_property(self, registry: CommandRegistry) -> None:
        """Свойство registered_commands возвращает список имён."""
        registry.register(DummyHandler("a"))
        registry.register(DummyHandler("b"))

        names = registry.registered_commands
        assert set(names) == {"a", "b"}


class TestSlashCommandRouter:
    """Тесты для SlashCommandRouter."""

    @pytest.mark.asyncio
    async def test_route_to_handler(self, registry: CommandRegistry, session: SessionState) -> None:
        """Маршрутизация команды к handler'у."""
        registry.register(DummyHandler("test"))
        router = SlashCommandRouter(registry)

        outcome = await router.route("test", ["arg1"], session)

        assert outcome is not None
        assert len(outcome.notifications) == 1
        # Проверяем содержимое notification - формат agent_message_chunk
        notif = outcome.notifications[0]
        assert notif.params is not None
        update = notif.params["update"]
        assert update["sessionUpdate"] == "agent_message_chunk"
        assert "Dummy executed" in update["content"]["text"]

    @pytest.mark.asyncio
    async def test_route_unknown_command_returns_none(
        self, registry: CommandRegistry, session: SessionState
    ) -> None:
        """Неизвестная команда возвращает None для fallback."""
        router = SlashCommandRouter(registry)

        outcome = await router.route("unknown", [], session)

        assert outcome is None


class TestStatusCommandHandler:
    """Тесты для StatusCommandHandler."""

    def test_execute_returns_session_info(self, session: SessionState) -> None:
        """Команда /status возвращает информацию о сессии."""
        handler = StatusCommandHandler()
        result = handler.execute([], session)

        assert len(result.content) == 1
        text = result.content[0]["text"]
        assert session.session_id in text
        assert "Состояние сессии" in text

    def test_get_definition(self) -> None:
        """Определение команды /status."""
        handler = StatusCommandHandler()
        definition = handler.get_definition()

        assert definition.name == "status"
        assert "состояние" in definition.description.lower()
        assert definition.input is None


class TestModeCommandHandler:
    """Тесты для ModeCommandHandler."""

    def test_show_current_mode(self, session: SessionState) -> None:
        """Без аргументов показывает текущий режим."""
        handler = ModeCommandHandler()
        result = handler.execute([], session)

        text = result.content[0]["text"]
        assert "bypass" in text
        assert "Текущий режим" in text

    def test_change_mode(self, session: SessionState) -> None:
        """С аргументом изменяет режим."""
        handler = ModeCommandHandler()
        result = handler.execute(["plan"], session)

        # Проверяем, что режим изменился
        assert session.config_values["mode"] == "plan"
        # Проверяем, что есть update для клиента
        assert len(result.updates) == 1
        assert result.updates[0]["sessionUpdate"] == "current_mode_update"
        assert result.updates[0]["mode"] == "plan"

    def test_invalid_mode(self, session: SessionState) -> None:
        """Неизвестный режим возвращает ошибку."""
        handler = ModeCommandHandler()
        result = handler.execute(["invalid_mode"], session)

        text = result.content[0]["text"]
        assert "Неизвестный режим" in text
        # Режим не изменился (остался bypass после миграции)
        assert session.config_values["mode"] == "bypass"

    def test_same_mode(self, session: SessionState) -> None:
        """Установка текущего режима сообщает, что режим уже активен."""
        handler = ModeCommandHandler()
        result = handler.execute(["bypass"], session)

        text = result.content[0]["text"]
        assert "уже активен" in text

    def test_get_definition(self) -> None:
        """Определение команды /mode."""
        handler = ModeCommandHandler()
        definition = handler.get_definition()

        assert definition.name == "mode"
        assert definition.input is not None
        assert "режим" in definition.input.hint.lower()


class TestHelpCommandHandler:
    """Тесты для HelpCommandHandler."""

    def test_list_all_commands(self, registry: CommandRegistry, session: SessionState) -> None:
        """Без аргументов показывает все команды."""
        registry.register(StatusCommandHandler())
        registry.register(ModeCommandHandler())

        # HelpCommandHandler нужно добавить после создания registry
        help_handler = HelpCommandHandler(registry)
        registry.register(help_handler)

        result = help_handler.execute([], session)

        text = result.content[0]["text"]
        assert "/status" in text
        assert "/mode" in text
        assert "/help" in text

    def test_help_for_specific_command(
        self, registry: CommandRegistry, session: SessionState
    ) -> None:
        """Справка по конкретной команде."""
        registry.register(StatusCommandHandler())
        help_handler = HelpCommandHandler(registry)
        registry.register(help_handler)

        result = help_handler.execute(["status"], session)

        text = result.content[0]["text"]
        assert "status" in text
        assert "Описание" in text

    def test_help_unknown_command(
        self, registry: CommandRegistry, session: SessionState
    ) -> None:
        """Справка по несуществующей команде."""
        help_handler = HelpCommandHandler(registry)

        result = help_handler.execute(["unknown"], session)

        text = result.content[0]["text"]
        assert "не найдена" in text

    def test_get_definition(self, registry: CommandRegistry) -> None:
        """Определение команды /help."""
        handler = HelpCommandHandler(registry)
        definition = handler.get_definition()

        assert definition.name == "help"
        assert definition.input is not None

    def test_list_includes_mcp_prompts(
        self, registry: CommandRegistry, session: SessionState
    ) -> None:
        """/help показывает MCP prompts из runtime registry."""
        from unittest.mock import MagicMock

        from codelab.server.models import AvailableCommand, AvailableCommandInput

        registry.register(StatusCommandHandler())
        help_handler = HelpCommandHandler(registry)
        registry.register(help_handler)

        # Создаём mock MCP prompt handler (из runtime registry)
        mock_handler = MagicMock()
        mock_handler.get_definition.return_value = AvailableCommand(
            name="code_review",
            description="Review code for best practices",
            input=AvailableCommandInput(hint="<language>"),
        )
        mcp_prompt_handlers = {"code_review": mock_handler}

        # Передаём handlers через execute_with_handlers
        result = help_handler.execute_with_handlers([], session, mcp_prompt_handlers)

        text = result.content[0]["text"]
        assert "/status" in text
        assert "/code_review" in text
        assert "Review code" in text

    def test_help_for_mcp_prompt_command(
        self, registry: CommandRegistry, session: SessionState
    ) -> None:
        """/help <command> работает для MCP prompt команд."""
        from unittest.mock import MagicMock

        from codelab.server.models import AvailableCommand, AvailableCommandInput

        help_handler = HelpCommandHandler(registry)

        # Создаём mock MCP prompt handler (из runtime registry)
        mock_handler = MagicMock()
        mock_handler.get_definition.return_value = AvailableCommand(
            name="plan_task",
            description="Plan a development task",
            input=AvailableCommandInput(hint="<task_name> [priority]"),
        )
        mcp_prompt_handlers = {"plan_task": mock_handler}

        # Передаём handlers через execute_with_handlers
        result = help_handler.execute_with_handlers(["plan_task"], session, mcp_prompt_handlers)

        text = result.content[0]["text"]
        assert "plan_task" in text
        assert "Plan a development task" in text
        assert "Описание" in text
