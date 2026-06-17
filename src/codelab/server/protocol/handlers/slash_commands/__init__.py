"""Модуль slash commands для ACP Protocol.

Содержит инфраструктуру для обработки slash-команд:
- CommandHandler: базовый класс для обработчиков команд
- CommandRegistry: реестр доступных команд
- SlashCommandRouter: маршрутизатор команд к обработчикам
"""

from .base import CommandHandler, CommandResult
from .registry import CommandRegistry
from .router import SlashCommandRouter

__all__ = [
    "CommandHandler",
    "CommandResult",
    "CommandRegistry",
    "SlashCommandRouter",
]
