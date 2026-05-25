"""Функция запуска ACP-сервера в stdio режиме.

Модуль содержит run_stdio_server() — аналог ACPHttpServer.run() для
stdio транспорта. Создаёт DI контейнер, ClientRPCService и запускает
цикл обработки сообщений через StdioServerTransport.

Обеспечивает одиночный экземпляр через fcntl.flock():
- При запуске захватывает блокировку на lock файл
- Если блокировка занята — убивает процесс-владелец и перехватывает
- При завершении — снимает блокировку

Пример использования:
    from codelab.server.transport.stdio_runner import run_stdio_server
    from codelab.server.storage import InMemoryStorage

    storage = InMemoryStorage()
    await run_stdio_server(storage=storage, config=AppConfig())
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import signal
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.config import AppConfig
from codelab.server.di import make_container
from codelab.server.messages import ACPMessage
from codelab.server.protocol.core import ACPProtocol
from codelab.server.rpc_holder import ClientRPCServiceHolder
from codelab.server.storage import SessionStorage
from codelab.server.transport.stdio import StdioServerTransport

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# Путь к lock файлу для stdio сервера
_LOCK_FILE = Path.home() / ".codelab" / "codelab-stdio.lock"

# Глобальная ссылка на lock файл — нужна для корректного закрытия
_lock_file_handle: Any = None


def _is_process_running(pid: int) -> bool:
    """Проверяет, запущен ли процесс с данным PID."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_pid_from_lock() -> int | None:
    """Читает PID из lock файла."""
    if not _LOCK_FILE.exists():
        return None
    try:
        return int(_LOCK_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def _acquire_singleton_lock() -> bool:
    """Захватывает блокировку одиночного экземпляра.

    Использует fcntl.flock() — атомарную операцию ОС.
    Если блокировка уже захвачена другим процессом:
    1. Читает PID владельца из lock файла
    2. Отправляет SIGTERM владельцу
    3. Ждёт завершения (до 3 секунд)
    4. При необходимости отправляет SIGKILL
    5. Повторяет попытку захвата

    Returns:
        True если блокировка успешно захвачена
    """
    global _lock_file_handle

    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Открываем lock файл (файл остаётся открытым для удержания блокировки)
    try:
        _lock_file_handle = open(_LOCK_FILE, "w")  # noqa: SIM115
    except OSError as e:
        logger.warning("failed to open lock file", error=str(e))
        return False

    # Пытаемся захватить блокировку (non-blocking)
    try:
        fcntl.flock(_lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Успех — записываем PID
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
        return True
    except OSError:
        # Блокировка занята — убиваем владельца
        owner_pid = _read_pid_from_lock()
        if owner_pid is not None and _is_process_running(owner_pid):
            logger.info("killing previous stdio server instance", pid=owner_pid)
            try:
                os.kill(owner_pid, signal.SIGTERM)
                # Ждём завершения
                for _ in range(30):
                    if not _is_process_running(owner_pid):
                        logger.info("previous stdio server stopped", pid=owner_pid)
                        break
                    time.sleep(0.1)
                else:
                    # Не завершился — SIGKILL
                    logger.warning(
                        "previous stdio server did not stop, sending SIGKILL",
                        pid=owner_pid,
                    )
                    os.kill(owner_pid, signal.SIGKILL)
                    time.sleep(0.2)
            except OSError as e:
                logger.warning(
                    "failed to kill previous stdio server",
                    pid=owner_pid,
                    error=str(e),
                )

        # Повторяем попытку захвата
        try:
            fcntl.flock(_lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _lock_file_handle.write(str(os.getpid()))
            _lock_file_handle.flush()
            return True
        except OSError:
            logger.error(
                "failed to acquire singleton lock after killing previous instance",
            )
            _lock_file_handle.close()
            _lock_file_handle = None
            return False


def _release_singleton_lock() -> None:
    """Снимает блокировку и удаляет lock файл."""
    global _lock_file_handle

    if _lock_file_handle is not None:
        try:
            fcntl.flock(_lock_file_handle, fcntl.LOCK_UN)
            _lock_file_handle.close()
        except OSError:
            pass
        _lock_file_handle = None

    _LOCK_FILE.unlink(missing_ok=True)


async def run_stdio_server(
    storage: SessionStorage,
    config: AppConfig,
    *,
    require_auth: bool = False,
    auth_api_key: str | None = None,
) -> None:
    """Запускает ACP-сервер в stdio режиме.

    Создаёт DI контейнер, ClientRPCService и запускает цикл обработки
    сообщений через StdioServerTransport.

    В stdio режиме:
    - Все JSON-RPC сообщения читаются из stdin
    - Все ответы записываются в stdout
    - Логи направляются в stderr
    - Web UI не запускается

    Args:
        storage: Хранилище сессий.
        config: Глобальная конфигурация приложения.
        require_auth: Требовать аутентификацию.
        auth_api_key: API ключ для аутентификации.
    """
    # Захватываем блокировку одиночного экземпляра
    if not _acquire_singleton_lock():
        logger.error("failed to acquire singleton lock, exiting")
        return

    logger.info(
        "starting stdio server",
        llm_provider=config.llm.provider,
        storage_type=type(storage).__name__,
        require_auth=require_auth,
    )

    # Создаём DI контейнер
    container = make_container(
        config=config,
        storage=storage,
        require_auth=require_auth,
        auth_api_key=auth_api_key,
    )

    # Создаём stdio транспорт
    transport = StdioServerTransport()

    # Создаём ClientRPCService для Agent→Client RPC
    # В stdio режиме RPC тоже идёт через stdout (тот же канал)
    async def send_rpc_request(request_dict: dict) -> None:
        """Отправляет JSON-RPC request клиенту через stdout."""
        message = ACPMessage.from_dict(request_dict)
        await transport.send(message)

    from codelab.server.client_rpc.service import ClientRPCService

    client_rpc_service = ClientRPCService(
        send_request_callback=send_rpc_request,
        client_capabilities={
            "fs": {
                "readTextFile": True,
                "writeTextFile": True,
            },
            "terminal": True,
        },
    )

    try:
        # Устанавливаем ClientRPCService в holder
        holder = await container.get(ClientRPCServiceHolder)
        holder.service = client_rpc_service

        # Создаём REQUEST scope и получаем ACPProtocol
        async with container() as request_scope:
            protocol = await request_scope.get(ACPProtocol)

            # Настраиваем send_callback для отправки сообщений из фоновых задач
            protocol._send_callback = transport.send

            # Запускаем цикл обработки через handle_and_process
            # чтобы фоновые задачи (pending_tool_execution) работали корректно
            async def on_message(acp_request: ACPMessage) -> Any:
                return await protocol.handle_and_process(acp_request)

            await transport.run(on_message=on_message)

    except asyncio.CancelledError:
        logger.info("stdio server cancelled")
    except Exception as exc:
        logger.error(
            "stdio server error",
            error=str(exc),
            exc_info=True,
        )
    finally:
        # Cleanup: отменяем pending RPC requests
        if client_rpc_service is not None:
            cancelled = client_rpc_service.cancel_all_pending_requests(
                reason="stdio server shutting down",
            )
            if cancelled > 0:
                logger.info(
                    "pending client rpc cancelled",
                    cancelled_rpc_count=cancelled,
                )

        # Закрываем DI контейнер
        await container.close()

        # Снимаем блокировку
        _release_singleton_lock()

        logger.info("stdio server stopped")
