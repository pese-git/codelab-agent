"""Модуль команд ACP-протокола.

Содержит реализацию Command Pattern для обработки ACP-методов.
Каждая команда инкапсулирует логику обработки одного метода.
"""

from .authenticate import AuthenticateCommandHandler
from .base import CommandHandler, CommandRegistry
from .initialize import InitializeCommandHandler
from .permission_response import PermissionResponseCommandHandler
from .session_cancel import SessionCancelCommandHandler
from .session_list import SessionListCommandHandler
from .session_load import SessionLoadCommandHandler
from .session_new import SessionNewCommandHandler
from .session_prompt import SessionPromptCommandHandler
from .set_config_option import SetConfigOptionCommandHandler
from .set_mode import SetModeCommandHandler

__all__ = [
    "AuthenticateCommandHandler",
    "CommandHandler",
    "CommandRegistry",
    "InitializeCommandHandler",
    "PermissionResponseCommandHandler",
    "SessionCancelCommandHandler",
    "SessionListCommandHandler",
    "SessionLoadCommandHandler",
    "SessionNewCommandHandler",
    "SessionPromptCommandHandler",
    "SetConfigOptionCommandHandler",
    "SetModeCommandHandler",
]
