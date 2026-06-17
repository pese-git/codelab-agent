"""Модальное окно просмотра текстового файла."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

if TYPE_CHECKING:
    from codelab.client.presentation.file_viewer_view_model import FileViewerViewModel


class FileViewerModal(ModalScreen[None]):
    """Показывает содержимое выбранного файла с подсветкой синтаксиса.

    Интегрирован с FileViewerViewModel для управления состоянием:
    - file_path: путь к просматриваемому файлу из ViewModel
    - content: содержимое файла из ViewModel
    - is_visible: видимость модального окна из ViewModel
    - is_loading: статус загрузки из ViewModel

    Все изменения UI синхронизируются с ViewModel через Observable паттерн.
    """

    BINDINGS = [
        ("ctrl+f", "focus_search", "Search"),
        ("f3", "next_match", "Next match"),
        ("shift+f3", "previous_match", "Prev match"),
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(
        self,
        *,
        file_viewer_vm: FileViewerViewModel,
        file_path: str | None = None,
        content: str | None = None,
    ) -> None:
        """Создает модальное окно просмотра файла.

        Args:
            file_viewer_vm: FileViewerViewModel для управления состоянием.
                Обязательный параметр для MVVM интеграции.
            file_path: Начальный путь файла (опционально).
                Если указан, используется вместо значения из ViewModel.
            content: Начальное содержимое файла (опционально).
                Если указан, используется вместо значения из ViewModel.
        """
        super().__init__()
        self.file_viewer_vm = file_viewer_vm

        # Если переданы параметры, инициализируем состояние в ViewModel
        if file_path and content:
            self.file_viewer_vm.show_file(Path(file_path), content)
            self._file_path = str(file_path)
            self._content = content
        else:
            # Получаем текущее состояние из ViewModel
            self._file_path = str(self.file_viewer_vm.file_path.value or "Неизвестный файл")
            self._content = self.file_viewer_vm.content.value or ""

        # Управление поиском в файле
        self._match_lines: list[int] = []
        self._active_match_index: int = -1

        # Сохраняем unsubscribe функции для очистки при уничтожении
        self._unsubscribers: list[Callable[[], None]] = []

        # Подписываемся на изменения ViewModel сразу (не только при on_mount)
        self._subscribe_to_view_model()

    def compose(self) -> ComposeResult:
        """Рендерит заголовок и подсвеченный контент файла."""

        with Vertical(id="file-viewer-modal"):
            yield Static(f"Файл: {self._file_path}", id="file-viewer-title")
            yield Input(
                placeholder="Поиск (Ctrl+F, Enter/F3 — далее, Shift+F3 — назад)",
                id="file-viewer-search",
            )
            yield Static("Поиск: введите текст", id="file-viewer-search-status")
            yield Static(self._build_syntax(), id="file-viewer-content")

    def on_mount(self) -> None:
        """Оставляет фокус на контенте файла при открытии модального окна."""
        self.query_one("#file-viewer-content", Static).focus()

    def _subscribe_to_view_model(self) -> None:
        """Подписаться на изменения ViewModel.

        Устанавливает observers на все Observable свойства ViewModel
        для синхронизации UI при изменениях состояния.
        """
        # Подписываемся на изменение пути файла
        unsub_path = self.file_viewer_vm.file_path.subscribe(self._on_file_path_changed)
        self._unsubscribers.append(unsub_path)

        # Подписываемся на изменение содержимого
        unsub_content = self.file_viewer_vm.content.subscribe(self._on_content_changed)
        self._unsubscribers.append(unsub_content)

        # Подписываемся на изменение статуса загрузки
        unsub_loading = self.file_viewer_vm.is_loading.subscribe(self._on_loading_changed)
        self._unsubscribers.append(unsub_loading)

    def _on_file_path_changed(self, new_path: Path | None) -> None:
        """Обработчик изменения пути файла в ViewModel.

        Args:
            new_path: Новый путь файла или None.
        """
        if new_path is None:
            return

        self._file_path = str(new_path)

        # Обновляем заголовок если компонент смонтирован
        try:
            title_widget = self.query_one("#file-viewer-title", Static)
            title_widget.update(f"Файл: {self._file_path}")
        except Exception:
            pass  # Компонент еще не смонтирован

    def _on_content_changed(self, new_content: str) -> None:
        """Обработчик изменения содержимого в ViewModel.

        Args:
            new_content: Новое содержимое файла.
        """
        self._content = new_content
        self._match_lines = []
        self._active_match_index = -1

        # Обновляем контент если компонент смонтирован
        try:
            content_widget = self.query_one("#file-viewer-content", Static)
            content_widget.update(self._build_syntax())
            # Сбрасываем поиск
            search_input = self.query_one("#file-viewer-search", Input)
            search_input.value = ""
            self._update_search_status()
        except Exception:
            pass  # Компонент еще не смонтирован

    def _on_loading_changed(self, is_loading: bool) -> None:
        """Обработчик изменения статуса загрузки в ViewModel.

        Args:
            is_loading: True если файл загружается.
        """
        # Здесь можно добавить логику отображения loading indicator
        pass

    def _unsubscribe_from_view_model(self) -> None:
        """Отписаться от всех изменений ViewModel."""
        for unsubscriber in self._unsubscribers:
            unsubscriber()
        self._unsubscribers.clear()

    def on_unmount(self) -> None:
        """Очистить подписки при удалении компонента."""
        self._unsubscribe_from_view_model()

    def action_close(self) -> None:
        """Закрывает окно просмотра файла по hotkey.

        Только обновляет ViewModel, NavigationManager сам удалит виджет.
        """
        self.file_viewer_vm.hide()

    def action_focus_search(self) -> None:
        """Переводит фокус в строку поиска по Ctrl+F."""

        search_input = self.query_one("#file-viewer-search", Input)
        search_input.focus()
        search_input.cursor_position = len(search_input.value)

    def action_next_match(self) -> None:
        """Переходит к следующему совпадению поискового запроса."""

        self._move_match(step=1)

    def action_previous_match(self) -> None:
        """Переходит к предыдущему совпадению поискового запроса."""

        self._move_match(step=-1)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Пересчитывает совпадения при каждом изменении строки поиска."""

        if event.input.id != "file-viewer-search":
            return
        self._rebuild_matches(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """По Enter в поиске переключает фокус на следующее совпадение."""

        if event.input.id != "file-viewer-search":
            return
        self._move_match(step=1)

    def _build_syntax(self) -> Syntax:
        """Создает Rich Syntax-блок с авто-определением языка по расширению."""

        guessed_language = Path(self._file_path).suffix.removeprefix(".")
        language = guessed_language if guessed_language else "text"
        return Syntax(
            self._content,
            language,
            line_numbers=True,
            word_wrap=False,
            indent_guides=True,
        )

    def _rebuild_matches(self, query: str) -> None:
        """Пересчитывает совпадения и обновляет статус поиска в модальном окне."""

        normalized_query = query.strip().lower()
        if not normalized_query:
            self._match_lines = []
            self._active_match_index = -1
            self._update_search_status()
            return

        self._match_lines = []
        for index, line in enumerate(self._content.splitlines(), start=1):
            if normalized_query in line.lower():
                self._match_lines.append(index)

        self._active_match_index = 0 if self._match_lines else -1
        self._update_search_status()
        self._scroll_to_active_match()

    def _move_match(self, *, step: int) -> None:
        """Сдвигает активный индекс совпадения и прокручивает контент к нему."""

        if not self._match_lines:
            self._update_search_status()
            return

        self._active_match_index = (self._active_match_index + step) % len(self._match_lines)
        self._update_search_status()
        self._scroll_to_active_match()

    def _update_search_status(self) -> None:
        """Показывает текущее состояние поиска и позицию в списке совпадений."""

        status_widget = self.query_one("#file-viewer-search-status", Static)
        if not self._match_lines:
            search_input = self.query_one("#file-viewer-search", Input)
            if search_input.value.strip():
                status_widget.update("Поиск: совпадений не найдено")
            else:
                status_widget.update("Поиск: введите текст")
            return

        current_position = self._active_match_index + 1
        total_matches = len(self._match_lines)
        current_line = self._match_lines[self._active_match_index]
        status_widget.update(f"Поиск: {current_position}/{total_matches}, строка {current_line}")

    def _scroll_to_active_match(self) -> None:
        """Прокручивает контент к активной строке совпадения."""

        if not self._match_lines:
            return

        content_widget = self.query_one("#file-viewer-content", Static)
        line_number = self._match_lines[self._active_match_index]
        content_widget.scroll_to(y=max(line_number - 2, 0), animate=False)
