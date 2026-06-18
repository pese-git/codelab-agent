"""ProgressBar - компонент прогресса.

Линейный индикатор прогресса:
- Determinate режим (известный прогресс)
- Indeterminate режим (неизвестный прогресс)
- Текст прогресса (%, шаги)
- Цветовые варианты
"""

from __future__ import annotations

import asyncio
import contextlib
from enum import Enum

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, Static


class ProgressVariant(Enum):
    """Цветовые варианты прогресс-бара."""

    DEFAULT = "default"
    PRIMARY = "primary"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class ProgressBar(Widget):
    """Линейный индикатор прогресса.

    Поддерживает determinate режим (с известным прогрессом)
    и indeterminate режим (анимированный индикатор загрузки).
    """

    DEFAULT_CSS = """
    ProgressBar {
        width: 100%;
        height: 3;
        layout: horizontal;
    }

    ProgressBar .progress-container {
        width: 1fr;
        height: 1;
        background: $surface;
        margin: 1 0;
    }

    ProgressBar .progress-fill {
        width: 0;
        height: 100%;
        background: $primary;
    }

    ProgressBar.-primary .progress-fill {
        background: $primary;
    }

    ProgressBar.-success .progress-fill {
        background: $success;
    }

    ProgressBar.-warning .progress-fill {
        background: $warning;
    }

    ProgressBar.-error .progress-fill {
        background: $error;
    }

    ProgressBar .progress-label {
        width: auto;
        min-width: 6;
        margin-left: 1;
        content-align: right middle;
    }

    ProgressBar.-no-label .progress-label {
        display: none;
    }

    ProgressBar.-indeterminate .progress-fill {
        width: 30%;
    }
    """

    # Текущий прогресс (0.0 - 1.0)
    progress: reactive[float] = reactive(0.0)

    # Indeterminate режим
    indeterminate: reactive[bool] = reactive(False)

    # Показывать ли метку с процентами
    show_label: reactive[bool] = reactive(True)

    def __init__(
        self,
        *,
        progress: float = 0.0,
        total: int | None = None,
        current: int | None = None,
        variant: ProgressVariant = ProgressVariant.DEFAULT,
        indeterminate: bool = False,
        show_label: bool = True,
        label_format: str = "{percent}%",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует прогресс-бар.

        Args:
            progress: Начальный прогресс (0.0 - 1.0)
            total: Общее количество шагов (для отображения шагов)
            current: Текущий шаг
            variant: Цветовой вариант
            indeterminate: Режим неизвестного прогресса
            show_label: Показывать метку с прогрессом
            label_format: Формат метки ({percent}, {current}, {total})
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id or "progress-bar", classes=classes)
        self._variant = variant
        self._total = total
        self._current = current
        self._label_format = label_format
        self._animation_task: asyncio.Task | None = None
        self._animation_offset: float = 0.0

        # Устанавливаем начальные значения
        self.progress = progress
        self.indeterminate = indeterminate
        self.show_label = show_label

        # Применяем вариант
        if variant != ProgressVariant.DEFAULT:
            self.add_class(f"-{variant.value}")

    def compose(self) -> ComposeResult:
        """Создаёт содержимое прогресс-бара."""
        with Horizontal():
            with Static(classes="progress-container"):
                yield Static(classes="progress-fill")
            yield Label(self._format_label(), classes="progress-label")

    @property
    def fill(self) -> Static:
        """Возвращает виджет заполнения."""
        return self.query_one(".progress-fill", Static)

    @property
    def label(self) -> Label:
        """Возвращает виджет метки."""
        return self.query_one(".progress-label", Label)

    def watch_progress(self, progress: float) -> None:
        """Обновляет отображение при изменении прогресса."""
        # Ограничиваем значение
        progress = max(0.0, min(1.0, progress))

        # Обновляем ширину заполнения
        try:
            fill = self.fill
            fill.styles.width = f"{int(progress * 100)}%"

            # Обновляем метку
            if self.show_label:
                self.label.update(self._format_label())
        except Exception:
            pass  # Виджет ещё не создан

    def watch_indeterminate(self, indeterminate: bool) -> None:
        """Обновляет режим при изменении indeterminate."""
        self.set_class(indeterminate, "-indeterminate")

        if indeterminate:
            self._start_animation()
        else:
            self._stop_animation()

    def watch_show_label(self, show: bool) -> None:
        """Обновляет видимость метки."""
        self.set_class(not show, "-no-label")

    def _format_label(self) -> str:
        """Форматирует текст метки."""
        percent = int(self.progress * 100)
        default_current = int(self.progress * (self._total or 100))
        current = self._current if self._current is not None else default_current
        total = self._total or 100

        return self._label_format.format(
            percent=percent,
            current=current,
            total=total,
        )

    def _start_animation(self) -> None:
        """Запускает анимацию indeterminate режима."""
        if self._animation_task:
            return

        async def animate() -> None:
            while True:
                self._animation_offset = (self._animation_offset + 5) % 100
                with contextlib.suppress(Exception):
                    self.fill.styles.margin = (0, 0, 0, int(self._animation_offset * 0.7))
                await asyncio.sleep(0.05)

        self._animation_task = asyncio.create_task(animate())

    def _stop_animation(self) -> None:
        """Останавливает анимацию."""
        if self._animation_task:
            self._animation_task.cancel()
            self._animation_task = None
            with contextlib.suppress(Exception):
                self.fill.styles.margin = (0, 0, 0, 0)

    def set_progress(self, value: float) -> None:
        """Устанавливает прогресс.

        Args:
            value: Значение прогресса (0.0 - 1.0)
        """
        self.progress = max(0.0, min(1.0, value))

    def advance(self, amount: float = 0.1) -> None:
        """Увеличивает прогресс на указанное значение.

        Args:
            amount: Значение для увеличения
        """
        self.progress = min(1.0, self.progress + amount)

    def set_steps(self, current: int, total: int) -> None:
        """Устанавливает прогресс в шагах.

        Args:
            current: Текущий шаг
            total: Общее количество шагов
        """
        self._current = current
        self._total = total
        self.progress = current / total if total > 0 else 0.0

    def reset(self) -> None:
        """Сбрасывает прогресс."""
        self.progress = 0.0
        self._current = None

    def complete(self) -> None:
        """Устанавливает прогресс в 100%."""
        self.progress = 1.0
        self.indeterminate = False

    def set_variant(self, variant: ProgressVariant) -> None:
        """Устанавливает цветовой вариант.

        Args:
            variant: Новый вариант
        """
        # Удаляем старый класс
        for v in ProgressVariant:
            self.remove_class(f"-{v.value}")

        # Добавляем новый
        if variant != ProgressVariant.DEFAULT:
            self.add_class(f"-{variant.value}")

        self._variant = variant

    async def on_unmount(self) -> None:
        """Останавливает анимацию при размонтировании."""
        self._stop_animation()
