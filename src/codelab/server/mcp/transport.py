"""Транспорты MCP — фасад пакета (обратная совместимость импортов).

Реализации разнесены по модулям base/stdio_transport/http_transport/sse_transport;
этот модуль сохраняет `from codelab.server.mcp.transport import ...`.
"""

from __future__ import annotations

from .base import MCPTransportError
from .http_transport import (
    HttpConnectionError,
    HttpTimeoutError,
    HttpTransport,
    HttpTransportError,
)
from .sse_transport import SseTransport, SseTransportError
from .stdio_transport import (
    ProcessExitedError,
    ProcessNotStartedError,
    StdioTransport,
    StdioTransportError,
)

__all__ = [
    "HttpConnectionError",
    "HttpTimeoutError",
    "HttpTransport",
    "HttpTransportError",
    "MCPTransportError",
    "ProcessExitedError",
    "ProcessNotStartedError",
    "SseTransport",
    "SseTransportError",
    "StdioTransport",
    "StdioTransportError",
]
