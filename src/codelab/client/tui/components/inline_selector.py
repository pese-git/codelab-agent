"""Inline dropdown selector для отображения текущих значений config options.

Отображает label и текущее значение с индикатором dropdown (▾).
Подписывается на Observable view_model для реактивных обновлений.
По клику или горячей клавише вызывает callback открытия модала.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from textual.widgets import Static

if TYPE_CHECKING:
    from codelab.client.presentation.observable import Observable


class InlineSelector(Static):
    """Inline dropdown selector для config options.

    Отображает ``label: current_value ▾`` и открывает модал выбора
    по клику или горячей клавише.

    Пример::

        >>> selector = InlineSelector(
        ...     label="Model",
        ...     get_label_fn=lambda: vm.get_current_model_label(),
        ...     observable=vm.current_model,
        ...     open_callback=lambda: app.action_select_model(),
        ...     hotkey="ctrl+m",
        ... )
    """

    DEFAULT_CSS = """
    InlineSelector {
        height: 100%;
        width: auto;
        min-width: 14;
        padding: 0 1;
        background: $surface;
        color: $foreground;
        border: round $border;
        text-style: bold;
    }

    InlineSelector:hover {
        background: $panel;
        border: round $primary;
    }

    InlineSelector.-active {
        border: round $primary;
    }
    """

    def __init__(
        self,
        label: str,
        get_label_fn: Callable[[], str],
        observable: Observable[Any] | None = None,
        open_callback: Callable[[], None] | None = None,
        hotkey: str | None = None,
        *,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
    ) -> None:
        """Инициализирует InlineSelector.

        Args:
            label: Отображаемый label (например, "Model", "Agent")
            get_label_fn: Функция получения текущего отображаемого значения
            observable: Observable для подписки на изменения (опционально)
            open_callback: Callback открытия модала выбора (опционально)
            hotkey: Горячая клавиша для открытия модала (опционально)
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._label = label
        self._get_label_fn = get_label_fn
        self._observable = observable
        self._open_callback = open_callback
        self._hotkey = hotkey
        self._unsubscribe: Callable[[], None] | None = None

        # Подписываемся сразу в __init__, чтобы получать обновления
        if self._observable is not None:
            self._unsubscribe = self._observable.subscribe(self._on_value_changed)

        self._update_display()

    def _update_display(self) -> None:
        """Обновляет отображаемый текст."""
        current = self._get_label_fn()
        self.update(f"{current} ▾")

    def _on_value_changed(self, _value: Any) -> None:
        """Обработчик изменения Observable значения."""
        self._update_display()

    def on_mount(self) -> None:
        """Обновляет отображение после монтирования (на случай задержки рендера)."""
        self._update_display()

    def on_unmount(self) -> None:
        """Отписывается от Observable при размонтировании."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    def on_click(self) -> None:
        """Обработка клика — открывает модал выбора."""
        if self._open_callback is not None:
            self._open_callback()

    def open_selector(self) -> None:
        """Программное открытие модала (для горячих клавиш)."""
        if self._open_callback is not None:
            self._open_callback()
