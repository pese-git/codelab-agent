"""Базовые абстракции для Command Pattern.

Определяет протоколы и интерфейсы для обработки ACP-методов
через паттерн Command с использованием Registry.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ...messages import ACPMessage
from ..state import ProtocolOutcome


@runtime_checkable
class CommandHandler(Protocol):
    """Протокол для обработчиков команд ACP-протокола.

    Каждый обработчик инкапсулирует логику обработки одного ACP-метода.
    Обработчики регистрируются в CommandRegistry и вызываются через
    единый интерфейс handle().

    Attributes:
        method_name: Имя ACP-метода, который обрабатывает этот handler.
    """

    method_name: str

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает входящее ACP-сообщение.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом обработки.
        """
        ...


class CommandRegistry:
    """Реестр обработчиков команд ACP-протокола.

    Управляет регистрацией и поиском обработчиков команд.
    Поддерживает регистрацию как стандартных ACP-методов,
    так и кастомных расширений (с префиксом '_').

    Пример использования:
        registry = CommandRegistry()
        registry.register(InitializeCommandHandler())
        registry.register(AuthenticateCommandHandler())

        handler = registry.get("initialize")
        if handler:
            result = await handler.handle(message)
    """

    def __init__(self) -> None:
        """Инициализирует пустой реестр команд."""
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, handler: CommandHandler) -> None:
        """Регистрирует обработчик команды.

        Args:
            handler: Обработчик команды с атрибутом method_name.

        Raises:
            ValueError: Если handler с таким method_name уже зарегистрирован.
        """
        if handler.method_name in self._handlers:
            raise ValueError(
                f"Handler for method '{handler.method_name}' is already registered"
            )
        self._handlers[handler.method_name] = handler

    def register_extension(self, handler: CommandHandler) -> None:
        """Регистрирует обработчик кастомного расширения.

        Кастомные методы должны начинаться с '_' согласно ACP Extensibility.

        Args:
            handler: Обработчик кастомного метода.

        Raises:
            ValueError: Если method_name не начинается с '_' или уже зарегистрирован.
        """
        if not handler.method_name.startswith("_"):
            raise ValueError(
                f"Extension method '{handler.method_name}' must start with '_'"
            )
        self.register(handler)

    def get(self, method: str) -> CommandHandler | None:
        """Возвращает обработчик для указанного метода.

        Args:
            method: Имя ACP-метода.

        Returns:
            Обработчик команды или None, если метод не зарегистрирован.
        """
        return self._handlers.get(method)

    def has(self, method: str) -> bool:
        """Проверяет, зарегистрирован ли обработчик для метода.

        Args:
            method: Имя ACP-метода.

        Returns:
            True, если обработчик зарегистрирован.
        """
        return method in self._handlers

    def unregister(self, method: str) -> None:
        """Удаляет обработчик для указанного метода.

        Args:
            method: Имя ACP-метода.
        """
        self._handlers.pop(method, None)

    def list_methods(self) -> list[str]:
        """Возвращает список всех зарегистрированных методов.

        Returns:
            Список имен зарегистрированных методов.
        """
        return list(self._handlers.keys())

    def clear(self) -> None:
        """Очищает все зарегистрированные обработчики."""
        self._handlers.clear()

    def __len__(self) -> int:
        """Возвращает количество зарегистрированных обработчиков."""
        return len(self._handlers)

    def __contains__(self, method: str) -> bool:
        """Проверяет наличие метода в реестре."""
        return self.has(method)
