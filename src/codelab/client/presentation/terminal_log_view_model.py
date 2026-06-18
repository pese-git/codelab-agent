"""ViewModel для управления логом терминала.

Отвечает за:
- Управление состоянием модального окна лога терминала
- Хранение записей лога
- Управление видимостью модального окна
"""

from __future__ import annotations

from typing import Any

from codelab.client.presentation.base_view_model import BaseViewModel
from codelab.client.presentation.observable import Observable


class TerminalLogViewModel(BaseViewModel):
    """ViewModel для отображения лога терминала.
    
    Управляет состоянием модального окна TerminalLogModal:
    - log_entries: список записей лога
    - is_visible: видимо ли модальное окно
    
    Все изменения делаются через методы ViewModel для обеспечения
    реактивности и контролируемого изменения состояния.
    
    Пример использования:
        >>> vm = TerminalLogViewModel()
        >>> vm.is_visible.subscribe(lambda v: print(f"Видим: {v}"))
        >>> 
        >>> # Добавить запись в лог
        >>> vm.add_entry("Command executed successfully")
        >>> 
        >>> # Показать модальное окно
        >>> vm.show()
        >>> 
        >>> # Скрыть
        >>> vm.hide()
    """
    
    def __init__(
        self,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        """Инициализировать TerminalLogViewModel.
        
        Args:
            event_bus: EventBus для публикации/подписки на события
            logger: Logger для структурированного логирования
        """
        super().__init__(event_bus, logger)
        # Список записей лога терминала
        self._log_entries: Observable[list[str]] = Observable([])
        # Видимо ли модальное окно
        self._is_visible: Observable[bool] = Observable(False)
    
    @property
    def log_entries(self) -> Observable:
        """Список записей лога.
        
        Returns:
            Observable со списком строк записей лога.
        """
        return self._log_entries
    
    @property
    def is_visible(self) -> Observable:
        """Видимо ли модальное окно.
        
        Returns:
            Observable с булевым значением видимости.
        """
        return self._is_visible
    
    def add_entry(self, entry: str) -> None:
        """Добавить запись в лог.
        
        Создает копию текущего списка, добавляет новую запись
        и обновляет Observable для уведомления подписчиков.
        
        Args:
            entry: Текст записи для добавления в лог.
        """
        self.logger.debug("adding_entry", entry=entry)
        current = self._log_entries.value.copy()
        current.append(entry)
        self._log_entries.value = current
    
    def set_entries(self, entries: list[str]) -> None:
        """Установить все записи лога.
        
        Заменяет все текущие записи на новый список.
        
        Args:
            entries: Новый список записей лога.
        """
        self.logger.debug("setting_entries", count=len(entries))
        self._log_entries.value = entries.copy()
    
    def clear_entries(self) -> None:
        """Очистить все записи.
        
        Удаляет все записи из лога.
        """
        self.logger.debug("clearing_entries")
        self._log_entries.value = []
    
    def show(self) -> None:
        """Показать модальное окно.
        
        Делает модальное окно видимым.
        """
        self.logger.debug("showing_terminal_log_modal")
        self._is_visible.value = True
    
    def hide(self) -> None:
        """Скрыть модальное окно.
        
        Скрывает модальное окно.
        """
        self.logger.debug("hiding_terminal_log_modal")
        self._is_visible.value = False
