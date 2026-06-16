"""Реестр slash commands.

CommandRegistry управляет списком доступных команд и их обработчиков.
Поддерживает динамическое добавление/удаление команд.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog

from codelab.server.models import AvailableCommand

from .base import CommandHandler

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()


class CommandRegistry:
    """Реестр доступных slash-команд.

    Хранит список команд и их обработчиков. Поддерживает:
    - Регистрацию handlers для команд
    - Динамическое добавление/удаление команд
    - Получение списка команд для отправки клиенту
    - Уведомление об изменениях через callback

    Пример использования:
        registry = CommandRegistry()
        registry.register(StatusCommandHandler())
        registry.register(HelpCommandHandler())

        commands = registry.get_commands(session)
        handler = registry.get_handler("status")
    """

    def __init__(self) -> None:
        """Инициализирует пустой реестр команд."""
        # Карта: имя команды -> handler
        self._handlers: dict[str, CommandHandler] = {}
        # Карта: имя команды -> определение (для динамических команд без handler)
        self._dynamic_commands: dict[str, AvailableCommand] = {}
        # Callback для уведомления об изменениях
        self._on_change_callback: Callable[[str], None] | None = None

    def register(self, handler: CommandHandler) -> None:
        """Регистрирует handler для команды.

        Handler предоставляет как логику выполнения, так и определение команды.

        Args:
            handler: Обработчик команды с get_definition()

        Raises:
            ValueError: Если команда с таким именем уже зарегистрирована
        """
        definition = handler.get_definition()
        name = definition.name

        if name in self._handlers:
            raise ValueError(f"Command '{name}' is already registered")

        self._handlers[name] = handler
        logger.debug("Registered slash command", command=name)

    def unregister(self, name: str) -> bool:
        """Удаляет регистрацию команды.

        Args:
            name: Имя команды для удаления

        Returns:
            True если команда была удалена, False если не найдена
        """
        if name in self._handlers:
            del self._handlers[name]
            logger.debug("Unregistered slash command", command=name)
            return True
        if name in self._dynamic_commands:
            del self._dynamic_commands[name]
            logger.debug("Removed dynamic slash command", command=name)
            return True
        return False

    def add_dynamic_command(self, command: AvailableCommand) -> None:
        """Добавляет динамическую команду без handler.

        Используется для команд, которые обрабатываются LLM агентом,
        а не встроенным handler'ом.

        Args:
            command: Определение команды
        """
        self._dynamic_commands[command.name] = command
        logger.debug("Added dynamic slash command", command=command.name)

    def get_handler(self, name: str) -> CommandHandler | None:
        """Возвращает handler для команды.

        Args:
            name: Имя команды

        Returns:
            Handler или None если команда не зарегистрирована или динамическая
        """
        return self._handlers.get(name)

    def has_handler(self, name: str) -> bool:
        """Проверяет наличие handler'а для команды.

        Args:
            name: Имя команды

        Returns:
            True если есть handler, False если нет или команда динамическая
        """
        return name in self._handlers

    def get_commands(self, session: SessionState | None = None) -> list[AvailableCommand]:
        """Возвращает список всех доступных команд.

        Args:
            session: Состояние сессии (для фильтрации контекстных команд)

        Returns:
            Список AvailableCommand для отправки в available_commands_update
        """
        commands: list[AvailableCommand] = []

        # Добавляем команды с handlers
        for handler in self._handlers.values():
            commands.append(handler.get_definition())

        # Добавляем динамические команды
        for command in self._dynamic_commands.values():
            commands.append(command)

        return commands

    def get_commands_as_dicts(
        self, session: SessionState | None = None
    ) -> list[dict[str, str | dict[str, str] | None]]:
        """Возвращает список команд в формате dict для JSON-RPC.

        Args:
            session: Состояние сессии (для фильтрации контекстных команд)

        Returns:
            Список dict с name, description, input (опционально)
        """
        commands = self.get_commands(session)
        result: list[dict[str, str | dict[str, str] | None]] = []

        for cmd in commands:
            entry: dict[str, str | dict[str, str] | None] = {
                "name": cmd.name,
                "description": cmd.description,
            }
            if cmd.input is not None:
                entry["input"] = {"hint": cmd.input.hint}
            result.append(entry)

        return result

    def set_on_change_callback(self, callback: Callable[[str], None] | None) -> None:
        """Устанавливает callback для уведомления об изменениях.

        Callback вызывается с session_id при добавлении/удалении команд.

        Args:
            callback: Функция (session_id: str) -> None или None для отключения
        """
        self._on_change_callback = callback

    def notify_change(self, session_id: str) -> None:
        """Уведомляет об изменении списка команд.

        Вызывает зарегистрированный callback, если установлен.

        Args:
            session_id: ID сессии для уведомления
        """
        if self._on_change_callback is not None:
            self._on_change_callback(session_id)

    @property
    def registered_commands(self) -> list[str]:
        """Возвращает список имён зарегистрированных команд."""
        return list(self._handlers.keys()) + list(self._dynamic_commands.keys())
