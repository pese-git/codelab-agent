"""Операции навигации для управления экранами и модальными окнами."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OperationType(Enum):
    """Типы операций навигации."""

    SHOW_SCREEN = "show_screen"
    HIDE_SCREEN = "hide_screen"
    RESET = "reset"


class OperationPriority(Enum):
    """Приоритеты операций (выше значение = выполнится раньше)."""

    LOW = 0
    NORMAL = 1
    HIGH = 2


@dataclass(frozen=True)
class NavigationOperation:
    """Описание операции навигации для очереди.

    Операции с более высоким приоритетом выполняются раньше операций
    с низким приоритетом. Внутри одного приоритета соблюдается FIFO порядок.
    """

    # Тип операции
    operation_type: OperationType

    # Параметры операции
    screen: Any | None = None  # Экран для show_screen
    screen_id: str | None = None  # ID экрана для hide_screen
    modal: bool = False  # Это ли модальное окно
    result: Any = None  # Результат для ModalScreen при hide

    # Контроль выполнения
    priority: int = 1  # Приоритет операции (выше = раньше)
    timeout_seconds: float = 30.0  # Таймаут на выполнение операции

    # Callbacks
    on_success: Callable[..., None] | None = None  # Вызовется при успехе
    on_error: Callable[[Exception], None] | None = None  # Вызовется при ошибке

    # Метаданные для отладки и логирования
    metadata: dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: "NavigationOperation") -> bool:
        """Сравнение по приоритету для очереди (обратный порядок).

        Используется heapq для приоритетной очереди.
        Более высокий приоритет = меньшее значение в очереди.
        """
        # Обратное сравнение для того, чтобы HIGH приоритет выполнялся первым
        return self.priority > other.priority
