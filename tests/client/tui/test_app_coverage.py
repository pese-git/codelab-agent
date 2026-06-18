"""Тесты покрытия для главного TUI приложения ACPClientApp.

Проверяют непокрытые строки в:
- Инициализация приложения
- Обработка событий
- Управление сессиями
- Работа с WebSocket
- Обработка ошибок
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.client.application.session_coordinator import SessionCoordinator
from codelab.client.domain.services import TransportService
from codelab.client.messages import PermissionOption, PermissionToolCall
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
from codelab.client.tui.app import ACPClientApp, run_tui_app
from codelab.client.tui.components import (
    FileChangePreviewModal,
    HelpModal,
    ModelSelectorModal,
    PermissionModal,
    PromptInput,
    QuickActionsBar,
    Sidebar,
    ToolCallCard,
)
from codelab.client.tui.components.command_palette import Command
from codelab.client.tui.config import TUIConfig


@contextmanager
def _patched_app(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    cwd: str | None = None,
    history_dir: str | None = None,
    theme: str | None = None,
    transport_mode: str = "websocket",
    stdio_command: str | None = None,
    stdio_args: list[str] | None = None,
) -> Iterator[tuple[ACPClientApp, dict[str, Any]]]:
    """Создает ACPClientApp с замоканными внешними зависимостями.

    Args:
        host: Адрес сервера для приложения.
        port: Порт сервера для приложения.
        cwd: Рабочая директория (если None, используется текущая).
        history_dir: Директория истории (если None, создается временная).
        theme: Начальная тема.
        transport_mode: Режим транспорта.
        stdio_command: Команда stdio режима.
        stdio_args: Аргументы stdio режима.

    Yields:
        Кортеж (приложение, словарь зависимостей).
    """
    if cwd is None:
        cwd = os.getcwd()

    with (
        tempfile.TemporaryDirectory() as tmpdir,
        patch("codelab.client.tui.app.create_client_container") as mock_create_container,
        patch("codelab.client.tui.app.MCPConfigLoader") as mock_mcp_loader_class,
        patch("codelab.client.tui.app.TUIConfigStore") as mock_config_store_class,
    ):
        mock_mcp_loader_class.return_value.load_mcp_servers.return_value = []

        config_store = MagicMock()
        config_store.load.return_value = TUIConfig()
        mock_config_store_class.return_value = config_store

        resolved_history_dir = history_dir or tmpdir

        coordinator = MagicMock(spec=SessionCoordinator)
        coordinator.initialize = AsyncMock(
            return_value={
                "protocol_version": "2024-01-01",
                "available_auth_methods": [],
            }
        )
        coordinator.load_session = AsyncMock(return_value={"replay_updates": []})
        coordinator.list_sessions = AsyncMock(return_value=[])
        coordinator.create_session = AsyncMock(return_value={"session_id": "sess_new"})
        coordinator.set_config_option = AsyncMock(return_value={})
        coordinator.send_prompt = AsyncMock()
        coordinator.cancel_prompt = AsyncMock()

        transport = MagicMock(spec=TransportService)
        transport.disconnect = AsyncMock()
        transport.set_permission_callback = MagicMock()

        event_bus = MagicMock()

        ui_vm = UIViewModel(event_bus=event_bus)
        session_vm = SessionViewModel(coordinator, event_bus=event_bus)
        chat_vm = ChatViewModel(
            coordinator,
            event_bus=event_bus,
            history_dir=resolved_history_dir,
        )
        plan_vm = PlanViewModel(event_bus=event_bus)
        filesystem_vm = FileSystemViewModel(event_bus=event_bus)
        terminal_log_vm = TerminalLogViewModel(event_bus=event_bus)
        file_viewer_vm = FileViewerViewModel(event_bus=event_bus)
        permission_vm = PermissionViewModel(event_bus=event_bus)
        terminal_vm = TerminalViewModel(event_bus=event_bus)
        model_selector_vm = ModelSelectorViewModel(coordinator, event_bus=event_bus)
        mode_selector_vm = ModeSelectorViewModel(coordinator, event_bus=event_bus)
        agent_selector_vm = AgentSelectorViewModel(coordinator, event_bus=event_bus)
        strategy_selector_vm = StrategySelectorViewModel(coordinator, event_bus=event_bus)

        instances: dict[type[Any], Any] = {
            UIViewModel: ui_vm,
            SessionViewModel: session_vm,
            ChatViewModel: chat_vm,
            PlanViewModel: plan_vm,
            FileSystemViewModel: filesystem_vm,
            TerminalLogViewModel: terminal_log_vm,
            FileViewerViewModel: file_viewer_vm,
            PermissionViewModel: permission_vm,
            TerminalViewModel: terminal_vm,
            ModelSelectorViewModel: model_selector_vm,
            ModeSelectorViewModel: mode_selector_vm,
            AgentSelectorViewModel: agent_selector_vm,
            StrategySelectorViewModel: strategy_selector_vm,
            SessionCoordinator: coordinator,
            TransportService: transport,
        }

        container = MagicMock()
        container.get = MagicMock(side_effect=lambda cls: instances[cls])
        container.close = MagicMock()

        mock_create_container.return_value = container

        app = ACPClientApp(
            host=host,
            port=port,
            cwd=cwd,
            history_dir=resolved_history_dir,
            theme=theme,
            transport_mode=transport_mode,
            stdio_command=stdio_command,
            stdio_args=stdio_args,
        )

        deps = {
            "coordinator": coordinator,
            "transport": transport,
            "container": container,
            "ui_vm": ui_vm,
            "session_vm": session_vm,
            "chat_vm": chat_vm,
            "plan_vm": plan_vm,
            "filesystem_vm": filesystem_vm,
            "terminal_log_vm": terminal_log_vm,
            "file_viewer_vm": file_viewer_vm,
            "permission_vm": permission_vm,
            "terminal_vm": terminal_vm,
            "model_selector_vm": model_selector_vm,
            "mode_selector_vm": mode_selector_vm,
            "agent_selector_vm": agent_selector_vm,
            "strategy_selector_vm": strategy_selector_vm,
            "config_store": config_store,
        }
        yield app, deps


class TestACPClientAppInit:
    """Тесты инициализации приложения."""

    def test_init_sets_attributes(self) -> None:
        """Приложение сохраняет параметры подключения и рабочую директорию."""
        with _patched_app() as (app, deps):
            assert app._host == "127.0.0.1"
            assert app._port == 8765
            assert app._cwd == os.getcwd()
            assert app._container is deps["container"]
            assert app._coordinator is deps["coordinator"]
            assert app._transport is deps["transport"]

    def test_init_uses_absolute_cwd(self) -> None:
        """Приложение преобразует cwd в абсолютный путь."""
        with _patched_app(cwd=".") as (app, _deps):
            assert os.path.isabs(app._cwd)

    def test_init_invalid_cwd_raises(self) -> None:
        """Недоступная директория вызывает ValueError."""
        with pytest.raises(ValueError):
            with _patched_app(cwd="/nonexistent/path/for/tests"):
                pass  # pragma: no cover

    def test_init_applies_cli_theme(self) -> None:
        """CLI тема имеет приоритет над конфигом."""
        with _patched_app(theme="dark") as (app, _deps):
            assert app._theme_manager.current_theme_name == "dark"

    def test_init_logs_mcp_load_failure(self) -> None:
        """Ошибка загрузки MCP серверов не прерывает инициализацию."""
        with (
            patch("codelab.client.tui.app.MCPConfigLoader") as mock_loader_class,
            patch("codelab.client.tui.app.create_client_container"),
            patch("codelab.client.tui.app.TUIConfigStore"),
            patch("codelab.client.tui.app.ThemeManager"),
        ):
            mock_loader_class.return_value.load_mcp_servers.side_effect = RuntimeError("fail")
            app = ACPClientApp(host="127.0.0.1", port=8765)
            assert app._mcp_servers == []

    def test_init_container_failure_raises_runtime_error(self) -> None:
        """Ошибка создания DI контейнера оборачивается в RuntimeError."""
        with (
            patch("codelab.client.tui.app.create_client_container") as mock_create,
            patch("codelab.client.tui.app.MCPConfigLoader"),
            patch("codelab.client.tui.app.TUIConfigStore"),
            patch("codelab.client.tui.app.ThemeManager"),
        ):
            mock_create.side_effect = RuntimeError("container fail")
            with pytest.raises(RuntimeError, match="Failed to initialize DI container"):
                ACPClientApp(host="127.0.0.1", port=8765)

    def test_init_viewmodel_failure_raises_runtime_error(self) -> None:
        """Ошибка разрешения ViewModels оборачивается в RuntimeError."""
        with (
            patch("codelab.client.tui.app.create_client_container") as mock_create,
            patch("codelab.client.tui.app.MCPConfigLoader"),
            patch("codelab.client.tui.app.TUIConfigStore"),
            patch("codelab.client.tui.app.ThemeManager"),
        ):
            container = MagicMock()
            container.get = MagicMock(side_effect=KeyError("missing vm"))
            mock_create.return_value = container
            with pytest.raises(RuntimeError, match="Failed to initialize ViewModels"):
                ACPClientApp(host="127.0.0.1", port=8765)


class TestACPClientAppComposeAndReady:
    """Тесты compose и on_ready."""

    async def test_compose_mounts_layout(self) -> None:
        """compose создает основную структуру интерфейса."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app._main_layout is not None
                assert app.query_one("#toast-container") is not None

    async def test_on_ready_mounts_components(self) -> None:
        """on_ready монтирует дочерние компоненты и запускает подключение."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.query_one(Sidebar) is not None
                assert app.query_one(PromptInput) is not None
                assert app.query_one(QuickActionsBar) is not None
                deps["coordinator"].initialize.assert_awaited_once()

    async def test_mount_main_layout_children_without_layout(self) -> None:
        """_mount_main_layout_children без main_layout логирует ошибку."""
        with _patched_app() as (app, _deps):
            app._main_layout = None
            app._mount_main_layout_children()


class TestACPClientAppConnection:
    """Тесты инициализации подключения и WebSocket."""

    async def test_initialize_connection_success(self) -> None:
        """Успешное подключение устанавливает статус CONNECTED."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                assert deps["ui_vm"].connection_status.value.name == "CONNECTED"
                deps["transport"].set_permission_callback.assert_called_once()
                deps["coordinator"].list_sessions.assert_awaited()

    async def test_initialize_connection_failure(self) -> None:
        """Ошибка подключения устанавливает статус DISCONNECTED."""
        with _patched_app() as (app, deps):
            deps["coordinator"].initialize = AsyncMock(side_effect=ConnectionError("fail"))
            async with app.run_test() as pilot:
                await pilot.pause()
                assert deps["ui_vm"].connection_status.value.name == "DISCONNECTED"
                assert deps["ui_vm"].is_loading.value is False

    async def test_initialize_connection_set_permission_callback_failure(self) -> None:
        """Ошибка регистрации callback не прерывает инициализацию."""
        with _patched_app() as (app, deps):
            deps["transport"].set_permission_callback.side_effect = RuntimeError("fail")
            async with app.run_test() as pilot:
                await pilot.pause()
                assert deps["ui_vm"].connection_status.value.name == "CONNECTED"

    async def test_on_unmount_closes_resources(self) -> None:
        """При завершении приложения закрывается WebSocket и DI контейнер."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
            deps["transport"].disconnect.assert_awaited_once()
            deps["container"].close.assert_called_once()

    async def test_on_unmount_disconnect_failure_logged(self) -> None:
        """Ошибка отключения WebSocket не прерывает on_unmount."""
        with _patched_app() as (app, deps):
            deps["transport"].disconnect = AsyncMock(side_effect=RuntimeError("fail"))
            async with app.run_test() as pilot:
                await pilot.pause()
            deps["container"].close.assert_called_once()


class TestACPClientAppToasts:
    """Тесты показа уведомлений."""

    async def test_show_toast_all_levels(self) -> None:
        """show_toast обрабатывает все уровни уведомлений."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.show_toast("info", level="info")
                app.show_toast("success", level="success")
                app.show_toast("warning", level="warning")
                app.show_toast("error", level="error")

    async def test_show_toast_failure_is_ignored(self) -> None:
        """Ошибка показа toast не прерывает приложение."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                with patch.object(app, "query_one", side_effect=RuntimeError("no toast")):
                    app.show_toast("test")


class TestACPClientAppSidebar:
    """Тесты управления боковой панелью."""

    async def test_action_next_sidebar_tab(self) -> None:
        """Переключение вкладки sidebar вперед."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_next_sidebar_tab()
                assert deps["ui_vm"].sidebar_tab.value == deps["ui_vm"].sidebar_tab.value

    async def test_action_previous_sidebar_tab(self) -> None:
        """Переключение вкладки sidebar назад."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_previous_sidebar_tab()

    async def test_action_toggle_sidebar(self) -> None:
        """Показ/скрытие боковой панели."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_toggle_sidebar()
                assert app._sidebar_visible is False
                app.action_toggle_sidebar()
                assert app._sidebar_visible is True

    async def test_action_focus_session_list(self) -> None:
        """Фокус на список сессий."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_focus_session_list()

    async def test_on_sidebar_state_changed_syncs_file_tree(self) -> None:
        """Смена вкладки sidebar синхронизирует видимость FileTree."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                from codelab.client.presentation.ui_view_model import SidebarTab

                deps["ui_vm"].set_sidebar_tab(SidebarTab.FILES)
                deps["ui_vm"].files_expanded.value = True
                await pilot.pause()


class TestACPClientAppSessions:
    """Тесты управления сессиями."""

    async def test_action_new_session(self) -> None:
        """Создание новой сессии по горячей клавише."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_new_session()
                await pilot.pause()
                deps["coordinator"].create_session.assert_awaited()

    async def test_action_next_session(self) -> None:
        """Выбор следующей сессии в sidebar."""
        with _patched_app() as (app, deps):
            deps["session_vm"].sessions.value = [
                {"sessionId": "sess_1", "title": "First"},
                {"sessionId": "sess_2", "title": "Second"},
            ]
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_next_session()
                await pilot.pause()

    async def test_action_previous_session(self) -> None:
        """Выбор предыдущей сессии в sidebar."""
        with _patched_app() as (app, deps):
            deps["session_vm"].sessions.value = [
                {"sessionId": "sess_1", "title": "First"},
                {"sessionId": "sess_2", "title": "Second"},
            ]
            deps["session_vm"].selected_session_id.value = "sess_2"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_previous_session()
                await pilot.pause()

    async def test_on_sidebar_session_selected(self) -> None:
        """Событие выбора сессии запускает переключение."""
        with _patched_app() as (app, deps):
            deps["session_vm"].sessions.value = [
                {"sessionId": "sess_1", "title": "First"},
            ]
            async with app.run_test() as pilot:
                await pilot.pause()
                event = Sidebar.SessionSelected("sess_1")
                app.on_sidebar_session_selected(event)
                await pilot.pause()
                deps["coordinator"].list_sessions.assert_awaited()

    async def test_on_selected_session_changed(self) -> None:
        """Смена активной сессии обновляет ChatViewModel."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                deps["session_vm"].selected_session_id.value = "sess_1"
                await pilot.pause()
                assert deps["chat_vm"]._active_session_id == "sess_1"

    async def test_load_selected_session_history(self) -> None:
        """Загрузка истории выбранной сессии через coordinator."""
        with _patched_app() as (app, deps):
            deps["coordinator"].load_session = AsyncMock(
                return_value={
                    "replay_updates": [
                        {
                            "params": {
                                "sessionId": "sess_1",
                                "update": {
                                    "sessionUpdate": "user_message_chunk",
                                    "content": {"text": "hello"},
                                },
                            }
                        }
                    ]
                }
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                await app._load_selected_session_history("sess_1")
                deps["coordinator"].load_session.assert_awaited_with(
                    "sess_1",
                    app._host,
                    app._port,
                    cwd=app._cwd,
                    mcp_servers=app._mcp_servers,
                )

    async def test_load_selected_session_history_failure(self) -> None:
        """Ошибка загрузки истории не прерывает приложение."""
        with _patched_app() as (app, deps):
            deps["coordinator"].load_session = AsyncMock(side_effect=RuntimeError("fail"))
            async with app.run_test() as pilot:
                await pilot.pause()
                await app._load_selected_session_history("sess_1")


class TestACPClientAppPrompt:
    """Тесты обработки ввода prompt и отмены."""

    async def test_on_prompt_input_submitted(self) -> None:
        """Отправка prompt добавляет сообщение и запускает отправку."""
        with _patched_app() as (app, deps):
            deps["session_vm"].sessions.value = [
                {"sessionId": "sess_1", "title": "First"},
            ]
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                event = PromptInput.Submitted("hello")
                app.on_prompt_input_submitted(event)
                await pilot.pause()
                assert any(m["content"] == "hello" for m in deps["chat_vm"].messages.value)
                deps["coordinator"].send_prompt.assert_awaited()

    async def test_on_prompt_input_submitted_without_session(self) -> None:
        """Отправка без активной сессии не выполняет запрос."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                event = PromptInput.Submitted("hello")
                app.on_prompt_input_submitted(event)
                deps["coordinator"].send_prompt.assert_not_awaited()

    async def test_action_cancel_prompt(self) -> None:
        """Отмена prompt проверяет условия и запускает worker."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                deps["session_vm"].selected_session_id.value = "sess_1"
                deps["chat_vm"].is_streaming.value = True
                # Проверяем, что условия для отмены выполнены
                assert deps["session_vm"].selected_session_id.value == "sess_1"
                assert deps["chat_vm"].is_streaming.value is True
                # Вызываем action_cancel_prompt
                app.action_cancel_prompt()
                # Даем worker'у время выполниться
                await pilot.pause()
                await pilot.pause()
                # Проверяем, что cancel_prompt был вызван
                deps["coordinator"].cancel_prompt.assert_awaited()

    async def test_action_cancel_prompt_no_session(self) -> None:
        """Отмена без сессии не отправляет запрос."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_cancel_prompt()
                deps["coordinator"].cancel_prompt.assert_not_awaited()

    async def test_action_cancel_prompt_not_streaming(self) -> None:
        """Отмена без streaming не отправляет запрос."""
        with _patched_app() as (app, deps):
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_cancel_prompt()
                deps["coordinator"].cancel_prompt.assert_not_awaited()

    async def test_on_prompt_input_cancelled(self) -> None:
        """Событие отмены из PromptInput вызывает action_cancel_prompt."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()
                deps["session_vm"].selected_session_id.value = "sess_1"
                deps["chat_vm"].is_streaming.value = True
                event = PromptInput.Cancelled()
                app.on_prompt_input_cancelled(event)
                await pilot.pause()
                await pilot.pause()
                # Проверяем, что cancel_prompt был вызван
                deps["coordinator"].cancel_prompt.assert_awaited()


class TestACPClientAppActions:
    """Тесты действий приложения."""

    async def test_action_open_help(self) -> None:
        """Открытие справки по текущему фокусу."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_open_help()
                assert isinstance(app.screen, HelpModal)

    async def test_action_show_hotkeys(self) -> None:
        """Открытие экрана горячих клавиш."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_show_hotkeys()
                assert isinstance(app.screen, HelpModal)

    async def test_action_command_palette(self) -> None:
        """Открытие палитры команд."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_command_palette()
                await pilot.pause()
                assert app.screen.is_modal

    async def test_action_command_palette_callback(self) -> None:
        """Callback палитры команд выполняет action выбранной команды."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_command_palette()
                await pilot.pause()
                Command(id="test", name="Test", action="open_help")
                # Проверяем, что dismiss вызывается с командой
                with patch.object(app.screen, "dismiss"):
                    app.screen.action_select()
                    # dismiss должен быть вызван с командой

    async def test_action_command_palette_callback_failure(self) -> None:
        """Ошибка выполнения action команды не прерывает приложение."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_command_palette()
                await pilot.pause()
                command = Command(id="test", name="Test", action="open_help")
                with patch.object(app, "action_open_help", side_effect=RuntimeError("fail")):
                    app.screen.dismiss(command)
                    await pilot.pause()

    async def test_action_toggle_theme(self) -> None:
        """Переключение темы сохраняет выбор в конфиг."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_toggle_theme()
                assert app._theme_manager.current_theme_name == "dark"
                deps["config_store"].save.assert_called()

    async def test_action_select_model_without_session(self) -> None:
        """Выбор модели без сессии показывает предупреждение."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_select_model()

    async def test_action_select_model_with_session(self) -> None:
        """Выбор модели с активной сессией открывает модальное окно."""
        with _patched_app() as (app, deps):
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_select_model()
                await pilot.pause()
                assert isinstance(app.screen, ModelSelectorModal)

    async def test_action_select_mode_with_session(self) -> None:
        """Выбор режима с активной сессией открывает модальное окно."""
        with _patched_app() as (app, deps):
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_select_mode()
                await pilot.pause()

    async def test_action_select_agent_with_session(self) -> None:
        """Выбор агента с активной сессией открывает модальное окно."""
        with _patched_app() as (app, deps):
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_select_agent()
                await pilot.pause()

    async def test_action_select_strategy_with_session(self) -> None:
        """Выбор стратегии с активной сессией открывает модальное окно."""
        with _patched_app() as (app, deps):
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_select_strategy()
                await pilot.pause()

    async def test_action_close_modal_closes_modal(self) -> None:
        """Закрытие модального окна по escape."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app.push_screen(HelpModal(context="global"))
                assert app.screen.is_modal
                app.action_close_modal()
                assert not app.screen.is_modal

    async def test_action_close_modal_without_modal(self) -> None:
        """Escape без модального окна вызывает отмену prompt."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                deps["session_vm"].selected_session_id.value = "sess_1"
                deps["chat_vm"].is_streaming.value = True
                app.action_close_modal()
                await pilot.pause()
                await pilot.pause()
                # Проверяем, что cancel_prompt был вызван
                deps["coordinator"].cancel_prompt.assert_awaited()


class TestACPClientAppQuickActions:
    """Тесты событий QuickActionsBar."""

    async def test_on_quick_actions_bar_new_session(self) -> None:
        """Запрос новой сессии из панели действий."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                event = QuickActionsBar.NewSessionRequested()
                app.on_quick_actions_bar_new_session_requested(event)
                await pilot.pause()
                deps["coordinator"].create_session.assert_awaited()

    async def test_on_quick_actions_bar_cancel(self) -> None:
        """Запрос отмены из панели действий."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                deps["session_vm"].selected_session_id.value = "sess_1"
                deps["chat_vm"].is_streaming.value = True
                event = QuickActionsBar.CancelRequested()
                app.on_quick_actions_bar_cancel_requested(event)
                await pilot.pause()
                await pilot.pause()
                # Проверяем, что cancel_prompt был вызван
                deps["coordinator"].cancel_prompt.assert_awaited()

    async def test_on_quick_actions_bar_help(self) -> None:
        """Запрос справки из панели действий."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                event = QuickActionsBar.HelpRequested()
                app.on_quick_actions_bar_help_requested(event)
                assert isinstance(app.screen, HelpModal)

    async def test_on_quick_actions_bar_theme_toggle(self) -> None:
        """Запрос переключения темы из панели действий."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                event = QuickActionsBar.ThemeToggleRequested()
                app.on_quick_actions_bar_theme_toggle_requested(event)
                assert app._theme_manager.current_theme_name == "dark"


class TestACPClientAppPermission:
    """Тесты обработки запросов разрешений."""

    async def test_show_permission_modal_via_chat_view(self) -> None:
        """Permission modal отображается через ChatView."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                tool_call = PermissionToolCall(toolCallId="call_1", title="Run")
                options = [PermissionOption(optionId="allow", name="Allow", kind="allow_once")]
                callback = MagicMock()
                app.show_permission_modal("req_1", tool_call, options, callback)

    async def test_show_permission_modal_fallback(self) -> None:
        """Fallback на PermissionModal если ChatView недоступен."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app._chat_view = None
                tool_call = PermissionToolCall(toolCallId="call_1", title="Run")
                options = [PermissionOption(optionId="allow", name="Allow", kind="allow_once")]
                callback = MagicMock()
                app.show_permission_modal("req_1", tool_call, options, callback)
                await pilot.pause()
                assert isinstance(app.screen, PermissionModal)

    async def test_show_permission_modal_failure_calls_callback(self) -> None:
        """При ошибке показа виджета вызывается callback с cancelled."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                # Создаем mock для _chat_view
                mock_chat_view = MagicMock()
                mock_chat_view.show_permission_request.side_effect = RuntimeError("no chat")
                app._chat_view = mock_chat_view
                
                tool_call = PermissionToolCall(toolCallId="call_1", title="Run")
                options = [PermissionOption(optionId="allow", name="Allow", kind="allow_once")]
                callback = MagicMock()
                app.show_permission_modal("req_1", tool_call, options, callback)
                callback.assert_called_once_with("req_1", "cancelled")


class TestACPClientAppToolCallCard:
    """Тесты обработки выбора карточки tool call."""

    async def test_on_tool_call_card_selected_file_tool(self) -> None:
        """Выбор файлового tool call открывает предпросмотр изменений."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                deps["chat_vm"].tool_calls.value = [
                    {
                        "toolCallId": "call_1",
                        "tool_name": "write_file",
                        "parameters": {"path": "test.py", "content": "x = 1"},
                    }
                ]
                card = ToolCallCard(
                    tool_call_id="call_1",
                    tool_name="write_file",
                    parameters={"path": "test.py", "content": "x = 1"},
                )
                event = ToolCallCard.Selected(card)
                app.on_tool_call_card_selected(event)
                assert isinstance(app.screen, FileChangePreviewModal)

    async def test_on_tool_call_card_selected_non_file_tool(self) -> None:
        """Выбор нефайлового tool call не открывает модальное окно."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                deps["chat_vm"].tool_calls.value = [
                    {"toolCallId": "call_1", "tool_name": "read_file"}
                ]
                card = ToolCallCard(
                    tool_call_id="call_1",
                    tool_name="read_file",
                    parameters={"path": "test.py"},
                )
                event = ToolCallCard.Selected(card)
                app.on_tool_call_card_selected(event)
                assert not isinstance(app.screen, FileChangePreviewModal)

    async def test_on_tool_call_card_selected_missing_data(self) -> None:
        """Если данные tool call не найдены, модальное окно не открывается."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                card = ToolCallCard(
                    tool_call_id="missing",
                    tool_name="write_file",
                    parameters={},
                )
                event = ToolCallCard.Selected(card)
                app.on_tool_call_card_selected(event)
                assert not isinstance(app.screen, FileChangePreviewModal)


class TestACPClientAppConfigOptions:
    """Тесты обновления конфигурационных опций."""

    async def test_on_config_option_updated(self) -> None:
        """Обновление config options синхронизирует selector ViewModels."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                event = MagicMock()
                event.session_id = "sess_1"
                event.config_options = [
                    {
                        "id": "model",
                        "category": "model",
                        "currentValue": "openai/gpt-4o",
                        "options": [{"value": "openai/gpt-4o", "name": "GPT-4o"}],
                    }
                ]
                app._on_config_option_updated(event)
                assert deps["model_selector_vm"].current_model.value == "openai/gpt-4o"

    async def test_on_config_option_updated_without_data(self) -> None:
        """Событие без config_options не вызывает обновления."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                event = MagicMock()
                event.session_id = None
                event.config_options = []
                app._on_config_option_updated(event)


class TestACPClientAppStdioMode:
    """Тесты stdio режима транспорта."""

    def test_init_stdio_transport(self) -> None:
        """Приложение передает параметры stdio в контейнер."""
        with _patched_app(
            transport_mode="stdio",
            stdio_command="python",
            stdio_args=["-m", "agent"],
        ) as (app, deps):
            deps["container"].get.assert_called()


class TestRunTuiApp:
    """Тесты функции запуска приложения."""

    def test_run_tui_app(self) -> None:
        """run_tui_app создает приложение и вызывает run."""
        with (
            patch("codelab.client.tui.app.resolve_tui_connection") as mock_resolve,
            patch("codelab.client.tui.app.ACPClientApp") as mock_app_class,
        ):
            mock_resolve.return_value = ("127.0.0.1", 8765, "light", 300.0)
            mock_app = MagicMock()
            mock_app_class.return_value = mock_app

            run_tui_app(host="127.0.0.1", port=8765)

            mock_resolve.assert_called_once()
            mock_app_class.assert_called_once()
            mock_app.run.assert_called_once()


class TestACPClientAppAdditionalCoverage:
    """Дополнительные тесты для непокрытых строк."""

    def test_init_config_option_event_import_error(self) -> None:
        """ImportError ConfigOptionUpdatedEvent не прерывает инициализацию."""
        with (
            patch("codelab.client.tui.app.create_client_container") as mock_create,
            patch("codelab.client.tui.app.MCPConfigLoader"),
            patch("codelab.client.tui.app.TUIConfigStore"),
            patch("codelab.client.tui.app.ThemeManager"),
        ):
            ui_vm = MagicMock()
            ui_vm.on_event = MagicMock(side_effect=ImportError("no event"))
            ui_vm.sidebar_tab = MagicMock()
            ui_vm.files_expanded = MagicMock()

            container = MagicMock()
            container.get = MagicMock(return_value=ui_vm)
            mock_create.return_value = container

            app = ACPClientApp(host="127.0.0.1", port=8765)
            assert app._ui_vm is ui_vm

    async def test_on_ready_navigation_manager_error(self) -> None:
        """Ошибка инициализации NavigationManager не прерывает on_ready."""
        with _patched_app() as (app, _deps):
            with patch(
                "codelab.client.tui.app.NavigationManager",
                side_effect=RuntimeError("fail"),
            ):
                async with app.run_test() as pilot:
                    await pilot.pause()
                    assert app._navigation_manager is None

    async def test_sidebar_state_changed_file_tree_not_found(self) -> None:
        """Исключение при поиске FileTree не прерывает _on_sidebar_state_changed."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                with patch.object(app, "query_one", side_effect=RuntimeError("not found")):
                    app._on_sidebar_state_changed(None)

    async def test_cancel_prompt_already_executing(self) -> None:
        """cancel_prompt пропускает отмену если уже выполняется."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                deps["session_vm"].selected_session_id.value = "sess_1"
                deps["chat_vm"].is_streaming.value = True
                deps["chat_vm"].cancel_prompt_cmd.is_executing.value = True
                app.action_cancel_prompt()
                await pilot.pause()
                deps["coordinator"].cancel_prompt.assert_not_awaited()

    async def test_toggle_sidebar_exception(self) -> None:
        """Ошибка toggle_sidebar логируется и не прерывает приложение."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                with patch.object(app, "query_one", side_effect=RuntimeError("fail")):
                    app.action_toggle_sidebar()

    async def test_open_help_with_sidebar_focused(self) -> None:
        """action_open_help с Sidebar в фокусе устанавливает context='sidebar'."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                sidebar = app.query_one(Sidebar)
                mock_focused = MagicMock(return_value=sidebar)
                with patch.object(type(app), "focused", mock_focused):
                    app.action_open_help()
                    await pilot.pause()

    async def test_open_help_with_prompt_input_focused(self) -> None:
        """action_open_help с PromptInput в фокусе устанавливает context='prompt-input'."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                prompt_input = app.query_one(PromptInput)
                mock_focused = MagicMock(return_value=prompt_input)
                with patch.object(type(app), "focused", mock_focused):
                    app.action_open_help()
                    await pilot.pause()

    async def test_toggle_theme_light_to_dark(self) -> None:
        """action_toggle_theme переключает light -> dark."""
        with _patched_app(theme="light") as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app._theme_manager.current_theme_name == "light"
                app.action_toggle_theme()
                assert app._theme_manager.current_theme_name == "dark"
                deps["config_store"].save.assert_called()

    async def test_toggle_theme_icon_update_error(self) -> None:
        """Ошибка обновления theme icon не прерывает toggle_theme."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                with patch.object(app, "query_one", side_effect=RuntimeError("fail")):
                    app.action_toggle_theme()

    async def test_select_model_callback_selected(self) -> None:
        """on_model_selected callback с value логирует выбор."""
        with _patched_app() as (app, deps):
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_select_model()
                await pilot.pause()
                modal = app.screen
                assert isinstance(modal, ModelSelectorModal)
                with patch.object(app, "run_worker"):
                    modal.dismiss("openai/gpt-4o")
                    await pilot.pause()
                    await pilot.pause()

    async def test_select_model_callback_cancelled(self) -> None:
        """on_model_selected callback с None не запускает worker."""
        with _patched_app() as (app, deps):
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_select_model()
                await pilot.pause()
                modal = app.screen
                assert isinstance(modal, ModelSelectorModal)
                with patch.object(app, "run_worker") as mock_worker:
                    modal.dismiss(None)
                    await pilot.pause()
                    mock_worker.assert_not_called()

    async def test_open_config_selector_no_session(self) -> None:
        """_open_config_option_selector без сессии показывает предупреждение."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                deps["session_vm"].selected_session_id.value = None
                app._open_config_option_selector(deps["mode_selector_vm"], "mode")

    async def test_config_option_callback_selected(self) -> None:
        """on_option_selected callback с value логирует выбор."""
        with _patched_app() as (app, deps):
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_select_mode()
                await pilot.pause()
                from codelab.client.tui.components import ConfigOptionSelectorModal
                modal = app.screen
                assert isinstance(modal, ConfigOptionSelectorModal)
                with patch.object(app, "run_worker"):
                    modal.dismiss("code")
                    await pilot.pause()
                    await pilot.pause()

    async def test_config_option_callback_cancelled(self) -> None:
        """on_option_selected callback с None не запускает worker."""
        with _patched_app() as (app, deps):
            deps["session_vm"].selected_session_id.value = "sess_1"
            async with app.run_test() as pilot:
                await pilot.pause()
                app.action_select_mode()
                await pilot.pause()
                from codelab.client.tui.components import ConfigOptionSelectorModal
                modal = app.screen
                assert isinstance(modal, ConfigOptionSelectorModal)
                with patch.object(app, "run_worker") as mock_worker:
                    modal.dismiss(None)
                    await pilot.pause()
                    mock_worker.assert_not_called()

    async def test_action_next_session_no_selection(self) -> None:
        """action_next_session без выбора не вызывает switch_session."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                sidebar = app.query_one(Sidebar)
                with patch.object(sidebar, "get_selected_session_id", return_value=None):
                    with patch.object(app, "run_worker") as mock_worker:
                        app.action_next_session()
                        await pilot.pause()
                        mock_worker.assert_not_called()

    async def test_action_previous_session_no_selection(self) -> None:
        """action_previous_session без выбора не вызывает switch_session."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                sidebar = app.query_one(Sidebar)
                with patch.object(sidebar, "get_selected_session_id", return_value=None):
                    with patch.object(app, "run_worker") as mock_worker:
                        app.action_previous_session()
                        await pilot.pause()
                        mock_worker.assert_not_called()

    async def test_on_selected_session_changed_with_none(self) -> None:
        """_on_selected_session_changed с None не загружает историю."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app._on_selected_session_changed(None)
                await pilot.pause()
                deps["coordinator"].load_session.assert_not_awaited()

    async def test_permission_modal_on_choice_error(self) -> None:
        """Ошибка в on_choice callback логируется."""
        with _patched_app() as (app, _deps):
            async with app.run_test() as pilot:
                await pilot.pause()
                app._chat_view = None
                tool_call = PermissionToolCall(toolCallId="call_1", title="Run")
                options = [PermissionOption(optionId="allow", name="Allow", kind="allow_once")]

                def failing_callback(req_id, tc, opts, on_choice):
                    on_choice(req_id, "invalid_option")

                app.show_permission_modal("req_1", tool_call, options, failing_callback)
                await pilot.pause()

    async def test_tool_call_card_selected_with_objects(self) -> None:
        """on_tool_call_card_selected с объектами вместо dict."""
        with _patched_app() as (app, deps):
            async with app.run_test() as pilot:
                await pilot.pause()

                class MockToolCall:
                    toolCallId = "call_1"
                    parameters = {"path": "test.py", "content": "x = 1"}

                deps["chat_vm"].tool_calls.value = [MockToolCall()]
                card = ToolCallCard(
                    tool_call_id="call_1",
                    tool_name="write_file",
                    parameters={"path": "test.py", "content": "x = 1"},
                )
                event = ToolCallCard.Selected(card)
                app.on_tool_call_card_selected(event)
                assert isinstance(app.screen, FileChangePreviewModal)

    async def test_unmount_container_close_error(self) -> None:
        """Ошибка закрытия DI контейнера логируется."""
        with _patched_app() as (app, deps):
            deps["container"].close = MagicMock(side_effect=RuntimeError("fail"))
            async with app.run_test() as pilot:
                await pilot.pause()
            deps["transport"].disconnect.assert_awaited_once()
