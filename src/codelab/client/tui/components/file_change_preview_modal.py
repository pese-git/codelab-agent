"""Модальное окно для отображения предпросмотра изменений файла.

Используется для показа diff при клике на tool call типа write_file/file_edit.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .file_change_preview import FileChangePreview


class FileChangePreviewModal(ModalScreen[None]):
    """Модальное окно для отображения предпросмотра изменений файла.
    
    Показывает diff между старым и новым содержимым файла
    с подсветкой добавленных и удалённых строк.
    
    Пример использования:
        >>> modal = FileChangePreviewModal(
        ...     file_path="/home/user/file.txt",
        ...     old_content="line1\\nline2",
        ...     new_content="line1\\nline3\\nline4",
        ... )
        >>> app.push_screen(modal)
    """

    BINDINGS = [
        Binding("escape", "close", "Закрыть"),
        Binding("q", "close", "Закрыть"),
    ]

    DEFAULT_CSS = """
    FileChangePreviewModal {
        align: center middle;
    }
    
    #file-change-modal-container {
        width: 80%;
        max-width: 120;
        height: 80%;
        max-height: 40;
        background: $surface;
        border: round $primary;
        padding: 1;
    }
    
    #file-change-modal-header {
        width: 100%;
        height: 1;
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }
    
    #file-change-modal-content {
        width: 100%;
        height: 1fr;
        overflow-y: auto;
    }
    
    #file-change-modal-footer {
        width: 100%;
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    
    #file-change-modal-footer Button {
        width: auto;
        min-width: 16;
    }
    """

    def __init__(
        self,
        file_path: str,
        *,
        old_content: str = "",
        new_content: str = "",
        tool_call_id: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Создаёт модальное окно предпросмотра изменений.
        
        Args:
            file_path: Путь к файлу
            old_content: Старое содержимое файла
            new_content: Новое содержимое файла
            tool_call_id: ID tool call (опционально)
            tool_name: Название инструмента (опционально)
        """
        super().__init__()
        self._file_path = file_path
        self._old_content = old_content
        self._new_content = new_content
        self._tool_call_id = tool_call_id
        self._tool_name = tool_name or "file_edit"

    @property
    def file_path(self) -> str:
        """Путь к файлу."""
        return self._file_path

    @property
    def tool_call_id(self) -> str | None:
        """ID tool call."""
        return self._tool_call_id

    def compose(self) -> ComposeResult:
        """Создаёт структуру модального окна."""
        with Vertical(id="file-change-modal-container"):
            # Заголовок с названием инструмента и путём к файлу
            header_text = f"🔧 {self._tool_name}: {self._file_path}"
            yield Static(header_text, id="file-change-modal-header")
            
            # Содержимое с diff preview
            with VerticalScroll(id="file-change-modal-content"):
                yield FileChangePreview(
                    file_path=self._file_path,
                    old_content=self._old_content,
                    new_content=self._new_content,
                    collapsed=False,  # Показываем развёрнутым в модальном окне
                    max_lines=100,  # Больше строк в модальном окне
                    id="file-change-preview",
                )
            
            # Кнопка закрытия
            with Vertical(id="file-change-modal-footer"):
                yield Button("Закрыть", variant="primary", id="close-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Обработчик нажатия кнопки.
        
        Args:
            event: Событие нажатия кнопки
        """
        if event.button.id == "close-button":
            self.dismiss()

    def action_close(self) -> None:
        """Закрыть модальное окно."""
        self.dismiss()
