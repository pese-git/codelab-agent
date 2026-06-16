"""ViewModel для управления терминальным выводом.

Отвечает за:
- Управление текстом вывода терминала
- Отслеживание статуса выполнения команды
- Очистку и добавление вывода
"""

from typing import Any

from codelab.client.presentation.base_view_model import BaseViewModel
from codelab.client.presentation.observable import Observable


class TerminalViewModel(BaseViewModel):
    """ViewModel для отображения терминального вывода.
    
    Хранит состояние терминала:
    - output: текущий текст вывода
    - has_output: есть ли непустой вывод
    - is_running: выполняется ли команда
    
    Пример использования:
        >>> vm = TerminalViewModel()
        >>> 
        >>> # Подписаться на изменения вывода
        >>> vm.output.subscribe(lambda text: print(f"Output: {text}"))
        >>> 
        >>> # Добавить вывод
        >>> vm.append_output("Hello ")
        >>> vm.append_output("World!")
        >>> 
        >>> # Установить статус выполнения
        >>> vm.set_running(True)
        >>> vm.set_running(False)
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        """Инициализировать TerminalViewModel.
        
        Args:
            event_bus: EventBus для публикации/подписки на события (опционально)
            logger: Logger для логирования (опционально)
        """
        super().__init__(event_bus, logger)
        
        # Observable свойства для состояния терминала
        self._output: Observable[str] = Observable("")
        self._has_output: Observable[bool] = Observable(False)
        self._is_running: Observable[bool] = Observable(False)

    @property
    def output(self) -> Observable:
        """Текст терминального вывода."""
        return self._output

    @property
    def has_output(self) -> Observable:
        """Есть ли непустой вывод в терминале."""
        return self._has_output

    @property
    def is_running(self) -> Observable:
        """Выполняется ли команда в данный момент."""
        return self._is_running

    def append_output(self, text: str) -> None:
        """Добавить текст к выводу.
        
        Args:
            text: Текст для добавления в конец вывода
        """
        current = self._output.value
        self._output.value = current + text
        self._has_output.value = bool(self._output.value.strip())

    def set_output(self, text: str) -> None:
        """Установить весь вывод.
        
        Args:
            text: Новый текст вывода (заменяет предыдущий)
        """
        self._output.value = text
        self._has_output.value = bool(text.strip())

    def clear_output(self) -> None:
        """Очистить вывод терминала."""
        self._output.value = ""
        self._has_output.value = False

    def set_running(self, running: bool) -> None:
        """Установить статус выполнения команды.
        
        Args:
            running: True если команда выполняется, False если завершена
        """
        self._is_running.value = running
