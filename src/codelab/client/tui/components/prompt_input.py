"""Поле ввода пользовательского промпта с inline-селекторами.

Вертикальный контейнер с двумя зонами:
- Верхняя: многострочное поле ввода с placeholder и кнопкой expand
- Нижняя: тулбар с inline-dropdown селекторами (Model, Session Mode, Agent, Strategy)
  и кнопками Send/Stop

Отвечает за:
- Ввод текста пользователя для отправки к модели
- Отображение текущих значений config options через InlineSelector
- Отправку prompt через ChatViewModel
- Управление историей промптов по сессиям
- Отключение/включение при streaming
- Expand/collapse поля ввода
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, TextArea

from .inline_selector import InlineSelector

if TYPE_CHECKING:
    from codelab.client.presentation.chat_view_model import ChatViewModel
    from codelab.client.presentation.config_option_selector_view_model import (
        ConfigOptionSelectorViewModel,
    )
    from codelab.client.presentation.model_selector_view_model import ModelSelectorViewModel

logger = structlog.get_logger("prompt_input")

PLACEHOLDER = "Type your task, use @ to add files or / for commands"


class PromptTextArea(TextArea):
    """Многострочное поле ввода текста промпта."""

    def __init__(self) -> None:
        """Инициализирует поле ввода."""
        super().__init__(id="prompt-textarea")

    async def _on_key(self, event: events.Key) -> None:
        """Обработка клавиш: Ctrl+Enter отправляет, Enter - новая строка."""
        key = event.key
        if key in ("ctrl+enter", "ctrl+j", "ctrl+m"):
            parent = self.parent
            while parent is not None:
                if isinstance(parent, PromptInput):
                    parent.action_submit()
                    event.prevent_default()
                    event.stop()
                    return
                parent = parent.parent
        await super()._on_key(event)


class PromptInput(Vertical):
    """Компонент ввода промпта с inline-селекторами и кнопками Send/Stop.

    Обязательно требует ChatViewModel для работы. Подписывается на Observable свойства:
    - is_streaming: флаг для disable/enable поля при streaming

    Принимает view_model для каждого селектора и callback для открытия модалов.
    """

    BINDINGS = [
        ("ctrl+enter", "submit", "Send"),
        ("ctrl+up", "history_previous", "Prev Prompt"),
        ("ctrl+down", "history_next", "Next Prompt"),
    ]

    class Submitted(Message):
        """Событие отправки текущего текста из поля ввода."""

        def __init__(self, text: str) -> None:
            """Сохраняет текст отправленного сообщения."""
            super().__init__()
            self.text = text

    class Cancelled(Message):
        """Событие отмены текущего запроса."""

    def __init__(
        self,
        chat_vm: ChatViewModel,
        model_selector_vm: ModelSelectorViewModel | None = None,
        mode_selector_vm: ConfigOptionSelectorViewModel | None = None,
        agent_selector_vm: ConfigOptionSelectorViewModel | None = None,
        strategy_selector_vm: ConfigOptionSelectorViewModel | None = None,
        open_model_callback: Any = None,
        open_mode_callback: Any = None,
        open_agent_callback: Any = None,
        open_strategy_callback: Any = None,
    ) -> None:
        """Инициализирует PromptInput.

        Args:
            chat_vm: ChatViewModel для управления состоянием
            model_selector_vm: ModelSelectorViewModel для селектора модели
            mode_selector_vm: ConfigOptionSelectorViewModel для селектора режима
            agent_selector_vm: ConfigOptionSelectorViewModel для селектора агента
            strategy_selector_vm: ConfigOptionSelectorViewModel для селектора стратегии
            open_model_callback: Callback открытия модала выбора модели
            open_mode_callback: Callback открытия модала выбора режима
            open_agent_callback: Callback открытия модала выбора агента
            open_strategy_callback: Callback открытия модала выбора стратегии
        """
        super().__init__(id="prompt-input")
        self.chat_vm = chat_vm
        self._model_selector_vm = model_selector_vm
        self._mode_selector_vm = mode_selector_vm
        self._agent_selector_vm = agent_selector_vm
        self._strategy_selector_vm = strategy_selector_vm
        self._open_model_callback = open_model_callback
        self._open_mode_callback = open_mode_callback
        self._open_agent_callback = open_agent_callback
        self._open_strategy_callback = open_strategy_callback
        self._active_session_id: str | None = None
        self._history_by_session: dict[str, list[str]] = {}
        self._history_index: int | None = None
        self._draft_text: str = ""
        self._text_area: PromptTextArea | None = None
        self._submit_button: Button | None = None
        self._stop_button: Button | None = None
        self._expand_button: Button | None = None
        self._is_expanded: bool = False
        self._model_selector: InlineSelector | None = None
        self._mode_selector: InlineSelector | None = None
        self._agent_selector: InlineSelector | None = None
        self._strategy_selector: InlineSelector | None = None

        self.chat_vm.is_streaming.subscribe(self._on_streaming_changed)

    DEFAULT_CSS = """
    PromptInput {
        background: $panel;
        border: round $border;
        padding: 0;
    }

    PromptInput:focus-within {
        border: round $primary;
    }

    #prompt-textarea-container {
        height: 6;
        width: 100%;
        layout: horizontal;
    }

    #prompt-textarea-container.expanded {
        height: 1fr;
    }

    #prompt-textarea {
        width: 1fr;
        height: 100%;
        background: transparent;
        border: none;
        color: $foreground;
    }

    #prompt-textarea:focus {
        border: none;
        background: transparent;
    }

    #expand-button {
        width: 3;
        height: 1;
        min-width: 3;
        background: transparent;
        border: none;
        color: $foreground-muted;
        content-align: center middle;
    }

    #expand-button:hover {
        color: $foreground;
    }

    #prompt-toolbar {
        height: 3;
        width: 100%;
        layout: horizontal;
        padding: 0 1;
    }

    #toolbar-selectors {
        height: 100%;
        width: 1fr;
        layout: horizontal;
    }

    #toolbar-actions {
        height: 100%;
        width: auto;
        layout: horizontal;
    }

    #add-button {
        width: 3;
        height: 100%;
        min-width: 3;
        background: transparent;
        border: none;
        color: $foreground-muted;
        content-align: center middle;
    }

    #add-button:hover {
        color: $foreground;
    }

    #submit-button {
        width: 8;
        height: 100%;
        margin-left: 1;
    }

    #stop-button {
        width: 8;
        height: 100%;
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Создаёт поле ввода, кнопку expand и тулбар с селекторами."""
        with Horizontal(id="prompt-textarea-container"):
            self._text_area = PromptTextArea()
            self._text_area.placeholder = PLACEHOLDER
            yield self._text_area

            self._expand_button = Button("↗", id="expand-button")
            yield self._expand_button

        with Horizontal(id="prompt-toolbar"):
            with Horizontal(id="toolbar-selectors"):
                self._add_button = Button("+", id="add-button")
                yield self._add_button

                self._model_selector = InlineSelector(
                    label="Model",
                    get_label_fn=self._get_model_label,
                    observable=(
                        self._model_selector_vm.current_model
                        if self._model_selector_vm
                        else None
                    ),
                    open_callback=self._open_model_callback,
                    hotkey="ctrl+m",
                    id="selector-model",
                )
                yield self._model_selector

                self._mode_selector = InlineSelector(
                    label="Session Mode",
                    get_label_fn=self._get_mode_label,
                    observable=(
                        self._mode_selector_vm.current_value
                        if self._mode_selector_vm
                        else None
                    ),
                    open_callback=self._open_mode_callback,
                    hotkey="ctrl+shift+m",
                    id="selector-mode",
                )
                yield self._mode_selector

                self._agent_selector = InlineSelector(
                    label="Agent",
                    get_label_fn=self._get_agent_label,
                    observable=(
                        self._agent_selector_vm.current_value
                        if self._agent_selector_vm
                        else None
                    ),
                    open_callback=self._open_agent_callback,
                    hotkey="ctrl+a",
                    id="selector-agent",
                )
                yield self._agent_selector

                self._strategy_selector = InlineSelector(
                    label="Strategy",
                    get_label_fn=self._get_strategy_label,
                    observable=(
                        self._strategy_selector_vm.current_value
                        if self._strategy_selector_vm
                        else None
                    ),
                    open_callback=self._open_strategy_callback,
                    hotkey="ctrl+shift+a",
                    id="selector-strategy",
                )
                yield self._strategy_selector

            with Horizontal(id="toolbar-actions"):
                self._submit_button = Button("Send", id="submit-button", variant="primary")
                yield self._submit_button

                self._stop_button = Button("Stop", id="stop-button", variant="error")
                yield self._stop_button

    def on_mount(self) -> None:
        """Скрываем Stop при монтировании."""
        if self._stop_button is not None:
            self._stop_button.display = False

    # --- Label getters ---

    def _get_model_label(self) -> str:
        if self._model_selector_vm:
            return self._model_selector_vm.get_current_model_label()
        return "Not set"

    def _get_mode_label(self) -> str:
        if self._mode_selector_vm:
            return self._mode_selector_vm.get_current_label()
        return "Not set"

    def _get_agent_label(self) -> str:
        if self._agent_selector_vm:
            return self._agent_selector_vm.get_current_label()
        return "Not set"

    def _get_strategy_label(self) -> str:
        if self._strategy_selector_vm:
            return self._strategy_selector_vm.get_current_label()
        return "Not set"

    # --- Expand ---

    def _toggle_expand(self) -> None:
        """Переключает высоту TextArea между обычной и развёрнутой."""
        self._is_expanded = not self._is_expanded
        container = self.query_one("#prompt-textarea-container")
        if self._is_expanded:
            container.add_class("expanded")
        else:
            container.remove_class("expanded")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Обработка нажатия кнопок."""
        if event.button.id == "submit-button":
            self.action_submit()
        elif event.button.id == "stop-button":
            if self._stop_button is not None:
                self._stop_button.display = False
            if self._submit_button is not None:
                self._submit_button.display = True
            logger.info("stop_button_pressed_posting_cancelled")
            self.post_message(self.Cancelled())
        elif event.button.id == "expand-button":
            self._toggle_expand()

    # --- Text access ---

    @property
    def text(self) -> str:
        """Возвращает текст из поля ввода."""
        if self._text_area is not None:
            return self._text_area.text
        return ""

    @text.setter
    def text(self, value: str) -> None:
        """Устанавливает текст в поле ввода."""
        if self._text_area is not None:
            self._text_area.text = value

    # --- Session history ---

    def set_active_session(self, session_id: str | None) -> None:
        """Переключает активный контекст истории промптов для текущей сессии."""
        self._active_session_id = session_id
        self._history_index = None
        self._draft_text = ""

    def remember_prompt(self, text: str) -> None:
        """Сохраняет отправленный prompt в историю активной сессии."""
        normalized = text.strip()
        if not normalized:
            return
        history = self._active_history()
        if history and history[-1] == normalized:
            return
        history.append(normalized)
        if len(history) > 100:
            del history[0]
        self._history_index = None
        self._draft_text = ""

    # --- Actions ---

    def action_submit(self) -> None:
        """Отправляет текст, если поле не пустое."""
        normalized = self.text.strip()
        if not normalized:
            return
        self.post_message(self.Submitted(normalized))

    def action_history_previous(self) -> None:
        """Подставляет предыдущий prompt из истории активной сессии."""
        history = self._active_history()
        if not history:
            return
        if self._history_index is None:
            self._draft_text = self.text
            self._history_index = len(history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        self.text = history[self._history_index]

    def action_history_next(self) -> None:
        """Переходит к более новому prompt или возвращает сохраненный черновик."""
        history = self._active_history()
        if not history or self._history_index is None:
            return
        if self._history_index < len(history) - 1:
            self._history_index += 1
            self.text = history[self._history_index]
            return
        self._history_index = None
        self.text = self._draft_text
        self._draft_text = ""

    # --- Streaming ---

    def _on_streaming_changed(self, is_streaming: bool) -> None:
        """Переключает Send/Stop и блокирует поле ввода при streaming."""
        logger.debug(
            "streaming_changed",
            is_streaming=is_streaming,
            submit_mounted=self._submit_button is not None,
            stop_mounted=self._stop_button is not None,
        )
        if self._text_area is not None:
            self._text_area.disabled = is_streaming
        if self._submit_button is not None:
            self._submit_button.display = not is_streaming
        if self._stop_button is not None:
            self._stop_button.display = is_streaming

    def _active_history(self) -> list[str]:
        """Возвращает список истории для активной сессии."""
        history_key = self._active_session_id or "__default__"
        if history_key not in self._history_by_session:
            self._history_by_session[history_key] = []
        return self._history_by_session[history_key]
