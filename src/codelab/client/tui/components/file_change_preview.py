"""Предпросмотр изменений в файле (diff view).

Референс OpenCode: packages/web/src/ui/file/diff.tsx

Отображает:
- Diff view: added (green), removed (red), unchanged
- Номера строк
- Collapse/expand для больших diff
"""

from __future__ import annotations

from typing import Literal

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Collapsible, Static

# Типы изменений строк
LineChangeType = Literal["added", "removed", "unchanged", "context"]


# Символы для типов изменений
CHANGE_SYMBOLS: dict[LineChangeType, str] = {
    "added": "+",
    "removed": "-",
    "unchanged": " ",
    "context": " ",
}


class DiffLine:
    """Представление одной строки diff."""
    
    def __init__(
        self,
        content: str,
        change_type: LineChangeType,
        old_line_number: int | None = None,
        new_line_number: int | None = None,
    ) -> None:
        """Создать строку diff.
        
        Args:
            content: Содержимое строки
            change_type: Тип изменения
            old_line_number: Номер строки в старой версии
            new_line_number: Номер строки в новой версии
        """
        self.content = content
        self.change_type = change_type
        self.old_line_number = old_line_number
        self.new_line_number = new_line_number


class FileChangePreview(Static):
    """Виджет предпросмотра изменений файла.
    
    Отображает diff между старой и новой версией файла
    с подсветкой добавленных и удалённых строк.
    
    Пример использования:
        >>> preview = FileChangePreview(
        ...     file_path="/home/user/file.txt",
        ...     old_content="line1\\nline2",
        ...     new_content="line1\\nline3\\nline4",
        ... )
    """

    DEFAULT_CSS = """
    FileChangePreview {
        width: 100%;
        height: auto;
        background: $surface;
        border: round $primary 30%;
        padding: 0;
    }
    
    #diff-header {
        width: 100%;
        height: 1;
        background: $primary 30%;
        padding: 0 1;
        text-style: bold;
    }
    
    #diff-stats {
        width: 100%;
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    
    #diff-content {
        width: 100%;
        height: auto;
        max-height: 20;
        overflow: auto;
    }
    
    .diff-line {
        width: 100%;
        height: 1;
    }
    
    .diff-line.added {
        background: $success 20%;
        color: $success;
    }
    
    .diff-line.removed {
        background: $error 20%;
        color: $error;
    }
    
    .diff-line.unchanged {
        color: $text-muted;
    }
    
    .line-number {
        width: 8;
        color: $text-muted 50%;
        text-align: right;
        padding-right: 1;
    }
    """

    def __init__(
        self,
        file_path: str,
        *,
        old_content: str = "",
        new_content: str = "",
        diff_lines: list[DiffLine] | None = None,
        collapsed: bool = False,
        max_lines: int = 50,
        show_line_numbers: bool = True,
        name: str | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
    ) -> None:
        """Создаёт виджет предпросмотра изменений.
        
        Args:
            file_path: Путь к файлу
            old_content: Старое содержимое файла
            new_content: Новое содержимое файла
            diff_lines: Готовые строки diff (если есть)
            collapsed: Изначально свёрнут
            max_lines: Максимум строк для отображения
            show_line_numbers: Показывать номера строк
            name: Имя виджета
            id: ID виджета
            classes: Дополнительные CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        
        self._file_path = file_path
        self._old_content = old_content
        self._new_content = new_content
        self._collapsed = collapsed
        self._max_lines = max_lines
        self._show_line_numbers = show_line_numbers
        
        # Вычисляем или используем готовые diff строки
        if diff_lines:
            self._diff_lines = diff_lines
        else:
            self._diff_lines = self._compute_diff()
        
        # Статистика
        self._added_count = sum(1 for line in self._diff_lines if line.change_type == "added")
        self._removed_count = sum(1 for line in self._diff_lines if line.change_type == "removed")
    
    @property
    def file_path(self) -> str:
        """Путь к файлу."""
        return self._file_path
    
    @property
    def added_count(self) -> int:
        """Количество добавленных строк."""
        return self._added_count
    
    @property
    def removed_count(self) -> int:
        """Количество удалённых строк."""
        return self._removed_count
    
    def _compute_diff(self) -> list[DiffLine]:
        """Вычислить diff между старым и новым содержимым.
        
        Returns:
            Список строк diff
        """
        # Простой алгоритм: сравниваем построчно
        old_lines = self._old_content.splitlines() if self._old_content else []
        new_lines = self._new_content.splitlines() if self._new_content else []
        
        result: list[DiffLine] = []
        
        # Используем простой LCS алгоритм для нахождения общих строк
        old_set = set(old_lines)
        new_set = set(new_lines)
        
        old_idx = 0
        
        # Проходим по новым строкам
        for i, line in enumerate(new_lines):
            if line in old_set and old_idx < len(old_lines):
                # Строка есть в обеих версиях - unchanged
                result.append(DiffLine(
                    content=line,
                    change_type="unchanged",
                    old_line_number=old_idx + 1,
                    new_line_number=i + 1,
                ))
                old_idx += 1
            else:
                # Строка только в новой версии - added
                result.append(DiffLine(
                    content=line,
                    change_type="added",
                    old_line_number=None,
                    new_line_number=i + 1,
                ))
        
        # Добавляем удалённые строки
        for i, line in enumerate(old_lines):
            if line not in new_set:
                result.append(DiffLine(
                    content=line,
                    change_type="removed",
                    old_line_number=i + 1,
                    new_line_number=None,
                ))
        
        return result
    
    def compose(self) -> ComposeResult:
        """Создаёт структуру виджета."""
        # Заголовок с путём файла
        yield Static(f"📄 {self._file_path}", id="diff-header")
        
        # Статистика изменений
        stats = f"+{self._added_count} -{self._removed_count}"
        yield Static(stats, id="diff-stats")
        
        # Содержимое diff
        title = f"Изменения ({len(self._diff_lines)} строк)"
        with Collapsible(title=title, collapsed=self._collapsed), Vertical(id="diff-content"):
            # Ограничиваем количество строк
            lines_to_show = self._diff_lines[:self._max_lines]
            
            for diff_line in lines_to_show:
                yield self._render_diff_line(diff_line)
            
            # Если есть ещё строки
            if len(self._diff_lines) > self._max_lines:
                remaining = len(self._diff_lines) - self._max_lines
                yield Static(f"... и ещё {remaining} строк", classes="diff-line unchanged")
    
    def _render_diff_line(self, diff_line: DiffLine) -> Static:
        """Создать виджет для строки diff.
        
        Args:
            diff_line: Строка diff
            
        Returns:
            Static виджет со строкой
        """
        # Форматируем номера строк
        line_prefix = ""
        if self._show_line_numbers:
            old_num = str(diff_line.old_line_number or "") if diff_line.old_line_number else ""
            new_num = str(diff_line.new_line_number or "") if diff_line.new_line_number else ""
            line_prefix = f"{old_num:>4} {new_num:>4} "
        
        # Символ изменения
        symbol = CHANGE_SYMBOLS.get(diff_line.change_type, " ")
        
        # Полный текст строки
        line_text = f"{line_prefix}{symbol} {diff_line.content}"
        
        return Static(line_text, classes=f"diff-line {diff_line.change_type}")
    
    def set_diff(
        self,
        old_content: str,
        new_content: str,
    ) -> None:
        """Установить новый diff.
        
        Args:
            old_content: Старое содержимое
            new_content: Новое содержимое
        """
        self._old_content = old_content
        self._new_content = new_content
        self._diff_lines = self._compute_diff()
        self._added_count = sum(
            1 for line in self._diff_lines if line.change_type == "added"
        )
        self._removed_count = sum(
            1 for line in self._diff_lines if line.change_type == "removed"
        )
        
        # Перерисовываем
        self.refresh()
    
    def collapse(self) -> None:
        """Свернуть diff."""
        self._collapsed = True
        try:
            collapsible = self.query_one(Collapsible)
            collapsible.collapsed = True
        except Exception:
            pass
    
    def expand(self) -> None:
        """Развернуть diff."""
        self._collapsed = False
        try:
            collapsible = self.query_one(Collapsible)
            collapsible.collapsed = False
        except Exception:
            pass
    
    def toggle(self) -> None:
        """Переключить состояние свёрнутости."""
        if self._collapsed:
            self.expand()
        else:
            self.collapse()
