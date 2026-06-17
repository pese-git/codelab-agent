"""Верхняя информационная панель приложения с интеграцией MVVM.

Референс: OpenCode packages/web/src/ui/header.tsx

Отвечает за отображение:
- Логотип/название слева
- Центр: breadcrumbs или title сессии
- Справа: статус соединения, настройки, текущая модель
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from codelab.client.presentation.model_selector_view_model import ModelSelectorViewModel
    from codelab.client.presentation.ui_view_model import ConnectionStatus, UIViewModel


class HeaderBar(Static):
    """Header с MVVM интеграцией для отображения статуса приложения.

    Структура по образцу OpenCode:
    - Left: логотип и название приложения
    - Center: breadcrumbs / title сессии
    - Right: статус соединения, индикатор загрузки, настройки

    Обязательно требует UIViewModel для работы. Подписывается на Observable свойства:
    - connection_status: текущий статус соединения
    - is_loading: флаг глобальной загрузки

    Примеры использования:
        >>> from codelab.client.presentation.ui_view_model import UIViewModel, ConnectionStatus
        >>> ui_vm = UIViewModel()
        >>> header = HeaderBar(ui_vm)
        >>>
        >>> # Когда UIViewModel обновляется, header обновляется автоматически
        >>> ui_vm.connection_status.value = ConnectionStatus.CONNECTED
    """

    # Настройки отображения
    APP_NAME = "CodeLab"
    APP_ICON = "⚡"

    def __init__(
        self,
        ui_vm: UIViewModel,
        model_selector_vm: ModelSelectorViewModel | None = None,
        *,
        session_title: str = "",
        show_breadcrumbs: bool = True,
    ) -> None:
        """Инициализирует HeaderBar с обязательным UIViewModel.

        Args:
            ui_vm: UIViewModel для управления состоянием header'a
            model_selector_vm: ModelSelectorViewModel для отображения модели
            session_title: Название текущей сессии
            show_breadcrumbs: Показывать ли breadcrumbs
        """
        super().__init__("", id="header")
        self.ui_vm = ui_vm
        self._model_selector_vm = model_selector_vm
        self._session_title = session_title
        self._show_breadcrumbs = show_breadcrumbs

        # Подписываемся на изменения в UIViewModel
        self.ui_vm.connection_status.subscribe(self._on_connection_status_changed)
        self.ui_vm.is_loading.subscribe(self._on_loading_changed)

        # Подписываемся на изменения модели если ViewModel доступен
        if self._model_selector_vm:
            self._model_selector_vm.current_model.subscribe(self._on_model_changed)

        # Инициализируем UI с текущим состоянием
        self._update_display()

    def _on_connection_status_changed(self, status: object) -> None:
        """Обновить header при изменении статуса соединения.

        Args:
            status: Новый статус соединения (ConnectionStatus enum)
        """
        self._update_display()

    def _on_loading_changed(self, is_loading: bool) -> None:
        """Обновить header при изменении статуса загрузки.

        Args:
            is_loading: True если идет загрузки, False иначе
        """
        self._update_display()

    def _on_model_changed(self, model: str | None) -> None:
        """Обновить header при изменении модели.

        Args:
            model: Новая модель или None
        """
        self._update_display()

    def _update_display(self) -> None:
        """Обновить отображение header'a на основе текущего состояния UIViewModel."""
        if self.ui_vm is None:
            return

        # Собираем части header'a
        left_part = self._build_left_part()
        center_part = self._build_center_part()
        right_part = self._build_right_part()

        # Форматируем строку с выравниванием
        display_text = f"{left_part} │ {center_part} │ {right_part}"
        self.update(display_text)

    def _build_left_part(self) -> str:
        """Собрать левую часть header'a: логотип и название."""
        return f"{self.APP_ICON} {self.APP_NAME}"

    def _build_center_part(self) -> str:
        """Собрать центральную часть header'a: breadcrumbs или title сессии."""
        if self._session_title:
            return f"📝 {self._session_title}"
        if self._show_breadcrumbs:
            return "Home"
        return ""

    def _build_right_part(self) -> str:
        """Собрать правую часть header'a: статус и индикаторы."""
        status = self.ui_vm.connection_status.value
        is_loading = self.ui_vm.is_loading.value

        # Формируем статус с иконкой
        status_icon = self._get_status_icon(status)
        status_text = status.value

        # Индикатор загрузки
        loading_indicator = "⟳ " if is_loading else ""

        parts = [f"{loading_indicator}{status_icon} {status_text}"]

        # Добавляем текущую модель если ViewModel доступен
        if self._model_selector_vm:
            model_label = self._model_selector_vm.get_current_model_label()
            if model_label and model_label != "Не выбрано":
                parts.append(f"🤖 {model_label}")

        return " │ ".join(parts)

    def _get_status_icon(self, status: ConnectionStatus) -> str:
        """Получить иконку для статуса соединения.

        Args:
            status: Статус соединения

        Returns:
            Иконка в виде emoji/символа
        """
        status_icons = {
            "connected": "🟢",
            "connecting": "🟡",
            "reconnecting": "🟡",
            "disconnected": "⚪",
            "error": "🔴",
        }
        return status_icons.get(status.value, "⚪")

    def set_session_title(self, title: str) -> None:
        """Установить заголовок текущей сессии.

        Args:
            title: Новый заголовок
        """
        self._session_title = title
        self._update_display()

    def set_breadcrumbs(self, breadcrumbs: list[str]) -> None:
        """Установить breadcrumbs для навигации.

        Args:
            breadcrumbs: Список элементов пути
        """
        self._session_title = " > ".join(breadcrumbs) if breadcrumbs else ""
        self._update_display()
