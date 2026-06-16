"""ClientRPCService для инициирования RPC вызовов на клиенте.

Модуль предоставляет сервис для безопасного и типизированного взаимодействия
с клиентом через JSON-RPC протокол.

Основной компонент:
    - ClientRPCService: Сервис для вызова методов на клиенте

Исключения:
    - ClientRPCError: Базовое исключение
    - ClientRPCTimeoutError: Timeout при ожидании ответа
    - ClientCapabilityMissingError: Клиент не поддерживает capability
    - ClientRPCResponseError: Ошибка от клиента

Модели:
    - ReadTextFileRequest, ReadTextFileResponse
    - WriteTextFileRequest, WriteTextFileResponse
    - TerminalCreateRequest, TerminalCreateResponse
    - TerminalOutputRequest, TerminalOutputResponse
    - TerminalWaitForExitRequest, TerminalWaitForExitResponse
    - TerminalKillRequest, TerminalKillResponse
    - TerminalReleaseRequest, TerminalReleaseResponse

Пример использования:
    async def send_request(request: dict) -> None:
        # Отправить JSON-RPC request на клиент через транспорт
        await transport.send(request)

    capabilities = {
        "fs": {"readTextFile": True, "writeTextFile": True},
        "terminal": True
    }

    rpc_service = ClientRPCService(
        send_request_callback=send_request,
        client_capabilities=capabilities,
        timeout=30.0
    )

    # Чтение файла
    content = await rpc_service.read_text_file(
        session_id="sess_123",
        path="/path/to/file.txt"
    )

    # Запуск команды
    terminal_id = await rpc_service.create_terminal(
        session_id="sess_123",
        command="python",
        args=["-c", "print('Hello')"]
    )

    # Получить output
    output, is_complete, exit_code = await rpc_service.terminal_output(
        session_id="sess_123",
        terminal_id=terminal_id
    )
"""

from __future__ import annotations

from .exceptions import (
    ClientCapabilityMissingError,
    ClientRPCCancelledError,
    ClientRPCError,
    ClientRPCResponseError,
    ClientRPCTimeoutError,
)
from .models import (
    ReadTextFileRequest,
    ReadTextFileResponse,
    TerminalCreateRequest,
    TerminalCreateResponse,
    TerminalKillRequest,
    TerminalKillResponse,
    TerminalOutputRequest,
    TerminalOutputResponse,
    TerminalReleaseRequest,
    TerminalReleaseResponse,
    TerminalWaitForExitRequest,
    TerminalWaitForExitResponse,
    WriteTextFileRequest,
    WriteTextFileResponse,
)
from .service import ClientRPCService

__all__ = [
    # Service
    "ClientRPCService",
    # Exceptions
    "ClientRPCError",
    "ClientRPCTimeoutError",
    "ClientRPCCancelledError",
    "ClientCapabilityMissingError",
    "ClientRPCResponseError",
    # Models - File System
    "ReadTextFileRequest",
    "ReadTextFileResponse",
    "WriteTextFileRequest",
    "WriteTextFileResponse",
    # Models - Terminal
    "TerminalCreateRequest",
    "TerminalCreateResponse",
    "TerminalOutputRequest",
    "TerminalOutputResponse",
    "TerminalWaitForExitRequest",
    "TerminalWaitForExitResponse",
    "TerminalKillRequest",
    "TerminalKillResponse",
    "TerminalReleaseRequest",
    "TerminalReleaseResponse",
]
