"""ClientProvider — декларативный DI-провайдер для сервисов клиента.

Заменяет DIBootstrapper и di_container. Использует dishka для
автоматического разрешения зависимостей и управления жизненным циклом.

Циклическая зависимость Coordinator ↔ PermissionHandler решается
через factory-метод, создающий оба объекта и связывающий их.

Пример использования:
    >>> from dishka import make_container, Scope
    >>> config = ClientConfig(host="localhost", port=8000, cwd=Path("/project"))
    >>> container = make_container(ClientProvider(), context={ClientConfig: config})
    >>> coordinator = container.get(SessionCoordinator)
"""

from dataclasses import dataclass
from typing import cast

import structlog
import structlog.stdlib
from dishka import Provider, Scope, provide

from codelab.client.application.permission_handler import PermissionHandler
from codelab.client.application.session_coordinator import SessionCoordinator
from codelab.client.domain.repositories import SessionRepository
from codelab.client.domain.services import TransportService
from codelab.client.infrastructure.client_config import ClientConfig
from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.infrastructure.handlers.file_system_handler import FileSystemHandler
from codelab.client.infrastructure.repositories import InMemorySessionRepository
from codelab.client.infrastructure.services.acp_transport.client_rpc_dispatcher import (
    ClientRpcDispatcher,
)
from codelab.client.infrastructure.services.acp_transport.contracts import RpcHandler
from codelab.client.infrastructure.services.acp_transport.handlers.fs_read_handler import (
    FsReadHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.fs_write_handler import (
    FsWriteHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.terminal_create_handler import (
    TerminalCreateHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.terminal_kill_handler import (
    TerminalKillHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.terminal_output_handler import (
    TerminalOutputHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.terminal_release_handler import (
    TerminalReleaseHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.terminal_wait_handler import (
    TerminalWaitHandler,
)
from codelab.client.infrastructure.services.acp_transport_service import (
    ACPTransportService,
    create_websocket_transport_service,
)
from codelab.client.infrastructure.services.file_system_executor import FileSystemExecutor
from codelab.client.infrastructure.services.terminal_executor import TerminalExecutor
from codelab.client.infrastructure.stdio_transport import StdioClientTransport
from codelab.client.presentation.chat.executors.fs_callback_executor import (
    FsCallbackExecutor,
)
from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalCallbackExecutor,
)
from codelab.client.presentation.chat.executors.terminal_executor_adapter import (
    TerminalExecutorAdapter,
)


@dataclass
class CoreServices:
    """Контейнер для Coordinator и PermissionHandler.

    Используется для разрыва циклической зависимости между
    SessionCoordinator и PermissionHandler при создании в dishka.
    """

    coordinator: SessionCoordinator
    permission_handler: PermissionHandler


class ClientProvider(Provider):
    """Провайдер сервисов клиентского приложения.

    Регистрирует все зависимости в порядке разрешения графа:
    1. EventBus — шина событий
    2. ACPTransportService — WebSocket транспорт
    3. InMemorySessionRepository — хранилище сессий
    4. FileSystemExecutor + FileSystemHandler — файловые операции
    5. TerminalExecutor — терминальные операции
    6. CoreServices (Coordinator + PermissionHandler) — оркестрация
    """

    scope = Scope.APP

    # =========================================================================
    # Базовые сервисы
    # =========================================================================

    @provide(scope=Scope.APP)
    def get_client_logger(self, config: ClientConfig) -> structlog.stdlib.BoundLogger:
        """Создаёт logger для всего клиентского приложения."""
        return config.logger or structlog.get_logger("client")  # type: ignore[return-value]

    @provide(scope=Scope.APP)
    def get_event_bus(self) -> EventBus:
        """Создаёт EventBus для слабой связанности компонентов."""
        return EventBus()

    @provide(scope=Scope.APP)
    def get_transport(
        self,
        config: ClientConfig,
        rpc_dispatcher: ClientRpcDispatcher,
    ) -> TransportService:
        """Создаёт ACPTransportService с правильным транспортом.

        Если config.transport_mode == "stdio" — использует StdioClientTransport.
        Иначе — WebSocketTransport.
        """
        if config.transport_mode == "stdio":
            transport = StdioClientTransport(
                command=config.stdio_command or "codelab",
                args=config.stdio_args or ["serve", "--stdio"],
                cwd=str(config.cwd),
                receive_timeout=config.receive_timeout,
            )
            return ACPTransportService(transport=transport, rpc_dispatcher=rpc_dispatcher)
        else:
            service = create_websocket_transport_service(
                host=config.host,
                port=config.port,
            )
            service._rpc_dispatcher = rpc_dispatcher
            return service

    @provide(scope=Scope.APP)
    def get_session_repo(self) -> SessionRepository:
        """Создаёт InMemorySessionRepository для хранения сессий."""
        return InMemorySessionRepository()

    # =========================================================================
    # Файловые операции
    # =========================================================================

    @provide(scope=Scope.APP)
    def get_fs_executor(self, config: ClientConfig) -> FileSystemExecutor:
        """Создаёт FileSystemExecutor с sandbox в cwd."""
        return FileSystemExecutor(base_path=config.cwd)

    @provide(scope=Scope.APP)
    def get_fs_handler(
        self, fs_executor: FileSystemExecutor
    ) -> FileSystemHandler:
        """Создаёт FileSystemHandler поверх FileSystemExecutor."""
        return FileSystemHandler(fs_executor)

    # =========================================================================
    # Терминальные операции
    # =========================================================================

    @provide(scope=Scope.APP)
    def get_terminal_executor(self) -> TerminalExecutor:
        """Создаёт TerminalExecutor для выполнения команд."""
        return TerminalExecutor()

    # =========================================================================
    # RPC обработчики и диспетчер
    # =========================================================================

    @provide(scope=Scope.APP)
    def get_fs_callback_executor_for_rpc(self, config: ClientConfig) -> FsCallbackExecutor:
        """Создаёт FsCallbackExecutor для RPC обработчиков."""
        return FsCallbackExecutor(config.cwd)

    @provide(scope=Scope.APP)
    def get_terminal_callback_executor_for_rpc(
        self, terminal_executor: TerminalExecutor
    ) -> TerminalCallbackExecutor:
        """Создаёт TerminalCallbackExecutor для RPC обработчиков."""
        adapter = TerminalExecutorAdapter(terminal_executor)
        return TerminalCallbackExecutor(adapter)

    @provide(scope=Scope.APP)
    def get_fs_read_handler(
        self, fs_executor: FsCallbackExecutor
    ) -> FsReadHandler:
        """Создаёт FsReadHandler для обработки fs/read_text_file."""
        return FsReadHandler(fs_executor)

    @provide(scope=Scope.APP)
    def get_fs_write_handler(
        self, fs_executor: FsCallbackExecutor
    ) -> FsWriteHandler:
        """Создаёт FsWriteHandler для обработки fs/write_text_file."""
        return FsWriteHandler(fs_executor)

    @provide(scope=Scope.APP)
    def get_terminal_create_handler(
        self, terminal_executor: TerminalCallbackExecutor
    ) -> TerminalCreateHandler:
        """Создаёт TerminalCreateHandler для обработки terminal/create."""
        return TerminalCreateHandler(terminal_executor)

    @provide(scope=Scope.APP)
    def get_terminal_output_handler(
        self, terminal_executor: TerminalCallbackExecutor
    ) -> TerminalOutputHandler:
        """Создаёт TerminalOutputHandler для обработки terminal/output."""
        return TerminalOutputHandler(terminal_executor)

    @provide(scope=Scope.APP)
    def get_terminal_wait_handler(
        self, terminal_executor: TerminalCallbackExecutor
    ) -> TerminalWaitHandler:
        """Создаёт TerminalWaitHandler для обработки terminal/wait_for_exit."""
        return TerminalWaitHandler(terminal_executor)

    @provide(scope=Scope.APP)
    def get_terminal_release_handler(
        self, terminal_executor: TerminalCallbackExecutor
    ) -> TerminalReleaseHandler:
        """Создаёт TerminalReleaseHandler для обработки terminal/release."""
        return TerminalReleaseHandler(terminal_executor)

    @provide(scope=Scope.APP)
    def get_terminal_kill_handler(
        self, terminal_executor: TerminalCallbackExecutor
    ) -> TerminalKillHandler:
        """Создаёт TerminalKillHandler для обработки terminal/kill."""
        return TerminalKillHandler(terminal_executor)

    @provide(scope=Scope.APP)
    def get_client_rpc_dispatcher(
        self,
        fs_read_handler: FsReadHandler,
        fs_write_handler: FsWriteHandler,
        terminal_create_handler: TerminalCreateHandler,
        terminal_output_handler: TerminalOutputHandler,
        terminal_wait_handler: TerminalWaitHandler,
        terminal_release_handler: TerminalReleaseHandler,
        terminal_kill_handler: TerminalKillHandler,
    ) -> ClientRpcDispatcher:
        """Создаёт ClientRpcDispatcher со всеми зарегистрированными обработчиками."""
        handlers: list[RpcHandler] = [
            fs_read_handler,
            fs_write_handler,
            terminal_create_handler,
            terminal_output_handler,
            terminal_wait_handler,
            terminal_release_handler,
            terminal_kill_handler,
        ]
        return ClientRpcDispatcher(handlers)

    # =========================================================================
    # Разрешение циклической зависимости Coordinator ↔ PermissionHandler
    # =========================================================================

    @provide(scope=Scope.APP)
    def create_core_services(
        self,
        transport: TransportService,
        session_repo: SessionRepository,
        logger: structlog.stdlib.BoundLogger,
    ) -> CoreServices:
        """Создаёт Coordinator и PermissionHandler, связывая их.

        Зависимость односторонняя: SessionCoordinator использует
        PermissionHandler для доступа к request_manager.
        ACPTransportService также получает ссылку через post-init.

        Двухфазная инициализация для post-init связывания:
        1. Создаём Coordinator с permission_handler=None
        2. Создаём PermissionHandler
        3. Устанавливаем permission_handler через setter методы
        """

        # Фаза 1: Coordinator без PermissionHandler
        coordinator = SessionCoordinator(
            transport=transport,
            session_repo=session_repo,
            permission_handler=None,
        )

        # Фаза 2: PermissionHandler (не зависит от coordinator)
        permission_handler = PermissionHandler(
            transport=transport,
            logger=logger,
        )

        # Связываем coordinator и transport с permission_handler через setter методы
        coordinator.set_permission_handler(permission_handler)
        # cast безопасен: единственная реализация TransportService — ACPTransportService
        acp_transport = cast(ACPTransportService, transport)
        acp_transport.set_permission_handler(permission_handler)

        return CoreServices(
            coordinator=coordinator,
            permission_handler=permission_handler,
        )

    @provide(scope=Scope.APP)
    def get_coordinator(self, core: CoreServices) -> SessionCoordinator:
        """Извлекает SessionCoordinator из CoreServices."""
        return core.coordinator

    @provide(scope=Scope.APP)
    def get_permission_handler(
        self, core: CoreServices
    ) -> PermissionHandler:
        """Извлекает PermissionHandler из CoreServices."""
        return core.permission_handler
