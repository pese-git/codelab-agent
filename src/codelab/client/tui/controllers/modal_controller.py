"""Контроллер открытия модальных окон TUI.

Инкапсулирует повторяющийся паттерн показа модалок-селекторов и предпросмотра:
guard «нет активной сессии» + toast, callback-замыкание с run_worker + toast,
push_screen. Держит ACPClientApp тонким (action_* сводятся к одному вызову).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..components import (
    CommandPalette,
    ConfigOptionSelectorModal,
    FileChangePreviewModal,
    HelpModal,
    ModelSelectorModal,
)
from .tool_call_parser import FileChange

if TYPE_CHECKING:
    from ...presentation.config_option_selector_view_model import (
        ConfigOptionSelectorViewModel,
    )
    from ...presentation.model_selector_view_model import ModelSelectorViewModel
    from ...presentation.session_view_model import SessionViewModel
    from ..app import ACPClientApp


class ModalController:
    """Открывает модалки-селекторы, палитру, справку и предпросмотр изменений."""

    def __init__(
        self,
        app: ACPClientApp,
        session_vm: SessionViewModel,
        logger: Any,
    ) -> None:
        self._app = app
        self._session_vm = session_vm
        self._logger = logger

    def _require_session(self, action: str) -> str | None:
        """Возвращает активную сессию либо показывает toast и None."""
        session_id = self._session_vm.selected_session_id.value
        if not session_id:
            self._logger.warning(f"{action}_no_active_session")
            self._app.show_toast("Сначала создайте или загрузите сессию", level="warning")
            return None
        return session_id

    def open_model_selector(self, model_selector_vm: ModelSelectorViewModel) -> None:
        """Открывает окно выбора LLM модели."""
        session_id = self._require_session("select_model")
        if session_id is None:
            return
        self._logger.debug("opening_model_selector", session_id=session_id)

        def on_model_selected(model_value: str | None) -> None:
            if model_value:
                self._logger.info("model_selected", session_id=session_id, model=model_value)
                self._app.run_worker(
                    model_selector_vm.select_model_cmd.execute(
                        session_id=session_id,
                        model_value=model_value,
                    ),
                    exclusive=False,
                )
                self._app.show_toast(
                    f"Модель изменена на {model_value.split('/')[-1]}", level="success"
                )
            else:
                self._logger.debug("model_selection_cancelled")

        self._app.push_screen(
            ModelSelectorModal(view_model=model_selector_vm, session_id=session_id),
            callback=on_model_selected,
        )

    def open_config_option(
        self,
        view_model: ConfigOptionSelectorViewModel,
        config_name: str,
    ) -> None:
        """Открывает универсальное окно выбора config option (mode/agent/strategy)."""
        session_id = self._require_session(f"select_{config_name}")
        if session_id is None:
            return
        self._logger.debug(f"opening_{config_name}_selector", session_id=session_id)

        def on_option_selected(option_value: str | None) -> None:
            if option_value:
                self._logger.info(
                    f"{config_name}_selected", session_id=session_id, value=option_value
                )
                self._app.run_worker(
                    view_model.select_option_cmd.execute(
                        session_id=session_id,
                        value=option_value,
                    ),
                    exclusive=False,
                )
                self._app.show_toast(
                    f"{view_model.title} изменён на {option_value}", level="success"
                )
            else:
                self._logger.debug(f"{config_name}_selection_cancelled")

        self._app.push_screen(
            ConfigOptionSelectorModal(view_model=view_model, session_id=session_id),
            callback=on_option_selected,
        )

    def open_command_palette(self) -> None:
        """Открывает палитру команд и выполняет выбранное действие."""
        self._logger.debug("opening_command_palette")

        def on_command_selected(result: object) -> None:
            if result is None:
                return
            from ..components import Command

            if isinstance(result, Command) and result.action:
                self._logger.debug(
                    "command_selected", command_id=result.id, action=result.action
                )
                try:
                    self._app.action(result.action)
                except Exception as e:
                    self._logger.warning(
                        "command_action_failed", action=result.action, error=str(e)
                    )

        self._app.push_screen(CommandPalette(), callback=on_command_selected)

    def open_help(self, context: str) -> None:
        """Открывает контекстную справку."""
        self._app.push_screen(HelpModal(context=context, show_hotkeys=False))

    def show_hotkeys(self) -> None:
        """Открывает экран со списком горячих клавиш."""
        self._app.push_screen(HelpModal(context="global", show_hotkeys=True))

    def open_file_change_preview(
        self,
        change: FileChange,
        tool_call_id: str,
        tool_name: str,
    ) -> None:
        """Показывает модалку предпросмотра изменения файла."""
        self._app.push_screen(
            FileChangePreviewModal(
                file_path=change.file_path,
                old_content=change.old_content,
                new_content=change.new_content,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
            )
        )
