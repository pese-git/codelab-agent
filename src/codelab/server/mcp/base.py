"""Базовое исключение иерархии MCP-транспортов.

`MCPTransportError` — корневой класс всех ошибок транспорта; от него наследуются
специфичные для протоколов исключения (`StdioTransportError`, `HttpTransportError`,
`SseTransportError`). Ловля `except MCPTransportError` перехватывает ошибку любого
транспорта.
"""

from __future__ import annotations


class MCPTransportError(Exception):
    """Корневое исключение для ошибок MCP-транспорта (Stdio/HTTP/SSE)."""

    pass
