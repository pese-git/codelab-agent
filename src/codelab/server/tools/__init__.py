"""Реестр инструментов и встроенные инструменты согласно ACP протоколу.

Включает инструменты для работы с файловой системой, терминалом и другие.
Структура:
- base: Базовые интерфейсы и типы
- registry: Реализация ToolRegistry
- executors: Асинхронные executors для инструментов
- integrations: Адаптеры для ClientRPC и PermissionManager
- definitions: Определения инструментов
"""

from codelab.server.tools.base import (
    ToolDefinition,
    ToolExecutionResult,
    ToolRegistry,
)
from codelab.server.tools.definitions import (
    FileSystemToolDefinitions,
    TerminalToolDefinitions,
)
from codelab.server.tools.executors import (
    FileSystemToolExecutor,
    TerminalToolExecutor,
    ToolExecutor,
)
from codelab.server.tools.integrations import ClientRPCBridge, PermissionChecker
from codelab.server.tools.registry import SimpleToolRegistry

__all__ = [
    "ToolRegistry",
    "ToolDefinition",
    "ToolExecutionResult",
    "SimpleToolRegistry",
    "ToolExecutor",
    "FileSystemToolExecutor",
    "TerminalToolExecutor",
    "ClientRPCBridge",
    "PermissionChecker",
    "FileSystemToolDefinitions",
    "TerminalToolDefinitions",
]
