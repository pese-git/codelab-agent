"""Обработчики для Agent->Client RPC методов.

Модуль содержит обработчики для методов, которые агент вызывает на клиенте:
- FileSystemHandler для fs/* методов
"""

from codelab.client.infrastructure.handlers.file_system_handler import FileSystemHandler

__all__ = [
    "FileSystemHandler",
]
