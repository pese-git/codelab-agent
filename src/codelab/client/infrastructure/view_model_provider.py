"""ViewModelProvider — декларативный DI-провайдер для ViewModels.

Заменяет ViewModelFactory. Регистрирует все ViewModels как
синглтоны (Scope.APP), автоматически разрешая зависимости.

Пример использования:
    >>> from dishka import make_container, Scope
    >>> container = make_container(ViewModelProvider())
    >>> ui_vm = container.get(UIViewModel)
"""

from pathlib import Path

import structlog.stdlib
from dishka import Provider, Scope, provide

from codelab.client.application.session_coordinator import SessionCoordinator
from codelab.client.infrastructure.client_config import ClientConfig
from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.infrastructure.services.terminal_executor import (
    TerminalExecutor,
)
from codelab.client.presentation.chat.dispatcher.session_update_dispatcher import (
    SessionUpdateDispatcher,
)
from codelab.client.presentation.chat.executors.fs_callback_executor import (
    FsCallbackExecutor,
)
from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalCallbackExecutor,
)
from codelab.client.presentation.chat.executors.terminal_executor_adapter import (
    TerminalExecutorAdapter,
)
from codelab.client.presentation.chat.handlers.config_option_handler import (
    ConfigOptionHandler,
)
from codelab.client.presentation.chat.handlers.message_chunk_handler import (
    MessageChunkHandler,
)
from codelab.client.presentation.chat.handlers.plan_update_handler import (
    PlanUpdateHandler,
)
from codelab.client.presentation.chat.handlers.tool_call_handler import (
    ToolCallHandler,
)
from codelab.client.presentation.chat.persistence.file_chat_persistence import (
    FileChatPersistence,
)
from codelab.client.presentation.chat_view_model import ChatViewModel
from codelab.client.presentation.config_option_selector_view_model import (
    AgentSelectorViewModel,
    ModeSelectorViewModel,
    StrategySelectorViewModel,
)
from codelab.client.presentation.file_viewer_view_model import FileViewerViewModel
from codelab.client.presentation.filesystem_view_model import FileSystemViewModel
from codelab.client.presentation.model_selector_view_model import ModelSelectorViewModel
from codelab.client.presentation.permission_view_model import PermissionViewModel
from codelab.client.presentation.plan_view_model import PlanViewModel
from codelab.client.presentation.session_view_model import SessionViewModel
from codelab.client.presentation.terminal_log_view_model import TerminalLogViewModel
from codelab.client.presentation.terminal_view_model import TerminalViewModel
from codelab.client.presentation.ui_view_model import UIViewModel


class ViewModelProvider(Provider):
    """Провайдер ViewModels клиентского приложения.

    Регистрирует ViewModels как синглтоны (Scope.APP):
    1. UIViewModel — глобальное UI состояние
    2. SessionViewModel — управление сессиями
    3. PlanViewModel — управление планом (создаётся до ChatViewModel)
    4. ChatViewModel — управление чатом (зависит от PlanViewModel)
    5. TerminalViewModel — управление терминалом
    6. FileSystemViewModel — управление файловой системой
    7. FileViewerViewModel — просмотр файлов
    8. PermissionViewModel — управление разрешениями
    9. TerminalLogViewModel — просмотр логов терминала
    10. ModelSelectorViewModel — выбор LLM модели
    11. ModeSelectorViewModel — выбор режима сессии
    12. AgentSelectorViewModel — выбор агента
    13. StrategySelectorViewModel — выбор стратегии выполнения

    Также регистрирует компоненты декомпозиции ChatViewModel:
    - SessionUpdateHandler'ы (MessageChunkHandler, ToolCallHandler, etc.)
    - SessionUpdateDispatcher
    - ChatPersistencePort (FileChatPersistence)
    - FsCallbackExecutor
    - TerminalCallbackExecutor
    """

    scope = Scope.APP

    # =========================================================================
    # Компоненты декомпозиции ChatViewModel
    # =========================================================================

    @provide(scope=Scope.APP)
    def get_message_chunk_handler(self) -> MessageChunkHandler:
        """Создаёт MessageChunkHandler для обработки message chunks."""
        return MessageChunkHandler()

    @provide(scope=Scope.APP)
    def get_tool_call_handler(self) -> ToolCallHandler:
        """Создаёт ToolCallHandler для обработки tool calls."""
        return ToolCallHandler()

    @provide(scope=Scope.APP)
    def get_plan_update_handler(self) -> PlanUpdateHandler:
        """Создаёт PlanUpdateHandler для обработки plan updates."""
        return PlanUpdateHandler()

    @provide(scope=Scope.APP)
    def get_config_option_handler(self) -> ConfigOptionHandler:
        """Создаёт ConfigOptionHandler для обработки config option updates."""
        return ConfigOptionHandler()

    @provide(scope=Scope.APP)
    def get_session_update_dispatcher(
        self,
        message_chunk_handler: MessageChunkHandler,
        tool_call_handler: ToolCallHandler,
        plan_update_handler: PlanUpdateHandler,
        config_option_handler: ConfigOptionHandler,
    ) -> SessionUpdateDispatcher:
        """Создаёт SessionUpdateDispatcher для маршрутизации обновлений."""
        return SessionUpdateDispatcher(
            message_chunk_handler=message_chunk_handler,
            tool_call_handler=tool_call_handler,
            plan_update_handler=plan_update_handler,
            config_option_handler=config_option_handler,
        )

    @provide(scope=Scope.APP)
    def get_chat_persistence(self, config: ClientConfig) -> FileChatPersistence:
        """Создаёт FileChatPersistence для сохранения истории чата."""
        if config.history_dir:
            history_dir = Path(config.history_dir)
        else:
            history_dir = Path.home() / ".codelab" / "data" / "history"
        return FileChatPersistence(history_dir)

    @provide(scope=Scope.APP)
    def get_fs_callback_executor(self, config: ClientConfig) -> FsCallbackExecutor:
        """Создаёт FsCallbackExecutor для async-safe FS операций."""
        return FsCallbackExecutor(config.cwd)

    @provide(scope=Scope.APP)
    def get_terminal_callback_executor(
        self, terminal_executor: TerminalExecutor
    ) -> TerminalCallbackExecutor:
        """Создаёт TerminalCallbackExecutor для управления терминалами."""
        # Адаптируем TerminalExecutor к TerminalExecutorPort
        adapter = TerminalExecutorAdapter(terminal_executor)
        return TerminalCallbackExecutor(adapter)

    # =========================================================================
    # ViewModels без зависимостей от координатора
    # =========================================================================

    @provide(scope=Scope.APP)
    def get_ui_vm(
        self,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> UIViewModel:
        """Создаёт UIViewModel для глобального UI состояния."""
        return UIViewModel(event_bus=event_bus, logger=logger)

    @provide(scope=Scope.APP)
    def get_plan_vm(
        self,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> PlanViewModel:
        """Создаёт PlanViewModel для управления планом."""
        return PlanViewModel(event_bus=event_bus, logger=logger)

    @provide(scope=Scope.APP)
    def get_terminal_vm(
        self,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> TerminalViewModel:
        """Создаёт TerminalViewModel для управления терминалом."""
        return TerminalViewModel(event_bus=event_bus, logger=logger)

    @provide(scope=Scope.APP)
    def get_filesystem_vm(
        self,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> FileSystemViewModel:
        """Создаёт FileSystemViewModel для управления файловой системой."""
        return FileSystemViewModel(event_bus=event_bus, logger=logger)

    @provide(scope=Scope.APP)
    def get_file_viewer_vm(
        self,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> FileViewerViewModel:
        """Создаёт FileViewerViewModel для просмотра файлов."""
        return FileViewerViewModel(event_bus=event_bus, logger=logger)

    @provide(scope=Scope.APP)
    def get_permission_vm(
        self,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> PermissionViewModel:
        """Создаёт PermissionViewModel для управления разрешениями."""
        return PermissionViewModel(event_bus=event_bus, logger=logger)

    @provide(scope=Scope.APP)
    def get_terminal_log_vm(
        self,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> TerminalLogViewModel:
        """Создаёт TerminalLogViewModel для просмотра логов терминала."""
        return TerminalLogViewModel(event_bus=event_bus, logger=logger)

    # =========================================================================
    # ViewModels с зависимостью от SessionCoordinator
    # =========================================================================

    @provide(scope=Scope.APP)
    def get_session_vm(
        self,
        coordinator: SessionCoordinator,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> SessionViewModel:
        """Создаёт SessionViewModel для управления сессиями."""
        return SessionViewModel(
            coordinator=coordinator,
            event_bus=event_bus,
            logger=logger,
        )

    @provide(scope=Scope.APP)
    def get_chat_vm(
        self,
        coordinator: SessionCoordinator,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
        plan_vm: PlanViewModel,
        session_update_dispatcher: SessionUpdateDispatcher,
        chat_persistence: FileChatPersistence,
        fs_callback_executor: FsCallbackExecutor,
        terminal_callback_executor: TerminalCallbackExecutor,
    ) -> ChatViewModel:
        """Создаёт ChatViewModel для управления чатом.

        Зависит от PlanViewModel для обработки plan updates.
        Компоненты декомпозиции регистрируются в этом провайдере.
        """
        return ChatViewModel(
            coordinator=coordinator,
            event_bus=event_bus,
            logger=logger,
            plan_vm=plan_vm,
            session_update_dispatcher=session_update_dispatcher,
            chat_persistence=chat_persistence,
            fs_callback_executor=fs_callback_executor,
            terminal_callback_executor=terminal_callback_executor,
        )

    @provide(scope=Scope.APP)
    def get_model_selector_vm(
        self,
        coordinator: SessionCoordinator,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> ModelSelectorViewModel:
        """Создаёт ModelSelectorViewModel для выбора LLM модели."""
        return ModelSelectorViewModel(
            coordinator=coordinator,
            event_bus=event_bus,
            logger=logger,
        )

    # =========================================================================
    # Специализированные ConfigOptionSelectorViewModel
    # =========================================================================

    @provide(scope=Scope.APP)
    def get_mode_selector_vm(
        self,
        coordinator: SessionCoordinator,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> ModeSelectorViewModel:
        """Создаёт ModeSelectorViewModel для выбора режима сессии."""
        return ModeSelectorViewModel(
            coordinator=coordinator,
            event_bus=event_bus,
            logger=logger,
        )

    @provide(scope=Scope.APP)
    def get_agent_selector_vm(
        self,
        coordinator: SessionCoordinator,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> AgentSelectorViewModel:
        """Создаёт AgentSelectorViewModel для выбора агента."""
        return AgentSelectorViewModel(
            coordinator=coordinator,
            event_bus=event_bus,
            logger=logger,
        )

    @provide(scope=Scope.APP)
    def get_strategy_selector_vm(
        self,
        coordinator: SessionCoordinator,
        event_bus: EventBus,
        logger: structlog.stdlib.BoundLogger,
    ) -> StrategySelectorViewModel:
        """Создаёт StrategySelectorViewModel для выбора стратегии выполнения."""
        return StrategySelectorViewModel(
            coordinator=coordinator,
            event_bus=event_bus,
            logger=logger,
        )
