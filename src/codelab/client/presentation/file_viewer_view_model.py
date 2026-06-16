"""ViewModel для управления просмотром файлов.

Отвечает за:
- Управление состоянием модального окна просмотра файла
- Хранение пути и содержимого файла
- Отслеживание статуса загрузки
- Управление видимостью модального окна
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codelab.client.presentation.base_view_model import BaseViewModel
from codelab.client.presentation.observable import Observable


class FileViewerViewModel(BaseViewModel):
    """ViewModel для отображения содержимого файла.
    
    Управляет состоянием модального окна FileViewerModal:
    - file_path: путь к просматриваемому файлу
    - content: содержимое файла
    - is_visible: видимо ли модальное окно
    - is_loading: загружается ли файл
    
    Все изменения делаются через методы ViewModel для обеспечения
    реактивности и контролируемого изменения состояния.
    
    Пример использования:
        >>> vm = FileViewerViewModel()
        >>> vm.file_path.subscribe(lambda p: print(f"Файл: {p}"))
        >>> vm.is_visible.subscribe(lambda v: print(f"Видим: {v}"))
        >>> 
        >>> # Показать файл
        >>> vm.show_file(Path("/home/user/main.py"), "print('Hello')")
        >>> 
        >>> # Скрыть
        >>> vm.hide()
    """
    
    def __init__(
        self,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        """Инициализировать FileViewerViewModel.
        
        Args:
            event_bus: EventBus для публикации/подписки на события
            logger: Logger для структурированного логирования
        """
        super().__init__(event_bus, logger)
        # Путь к просматриваемому файлу
        self._file_path: Observable[Path | None] = Observable(None)
        # Содержимое файла
        self._content: Observable[str] = Observable("")
        # Видимо ли модальное окно
        self._is_visible: Observable[bool] = Observable(False)
        # Загружается ли файл
        self._is_loading: Observable[bool] = Observable(False)
    
    @property
    def file_path(self) -> Observable:
        """Путь к просматриваемому файлу.
        
        Returns:
            Observable с Path объектом или None если файл не загружен.
        """
        return self._file_path
    
    @property
    def content(self) -> Observable:
        """Содержимое файла.
        
        Returns:
            Observable со строкой содержимого файла.
        """
        return self._content
    
    @property
    def is_visible(self) -> Observable:
        """Видимо ли модальное окно.
        
        Returns:
            Observable с флагом видимости модального окна.
        """
        return self._is_visible
    
    @property
    def is_loading(self) -> Observable:
        """Загружается ли файл.
        
        Returns:
            Observable с флагом загрузки файла.
        """
        return self._is_loading
    
    def show_file(self, path: Path, content: str) -> None:
        """Показать файл в модальном окне.
        
        Обновляет путь файла, содержимое и делает окно видимым.
        Также сбрасывает статус загрузки на False.
        
        Args:
            path: Путь к файлу (объект Path).
            content: Содержимое файла (строка).
        """
        self.logger.debug("showing_file", file_path=str(path))
        self._file_path.value = path
        self._content.value = content
        self._is_visible.value = True
        self._is_loading.value = False
    
    def set_loading(self, loading: bool) -> None:
        """Установить статус загрузки файла.
        
        Args:
            loading: True если файл загружается, False если загрузка завершена.
        """
        self.logger.debug("setting_loading_status", loading=loading)
        self._is_loading.value = loading
    
    def hide(self) -> None:
        """Скрыть модальное окно.
        
        Делает модальное окно невидимым без очистки состояния.
        Состояние (путь, содержимое) сохраняется.
        """
        self.logger.debug("hiding_file_viewer_modal")
        self._is_visible.value = False
    
    def clear(self) -> None:
        """Очистить состояние модального окна.
        
        Сбрасывает все свойства в начальное состояние:
        - file_path = None
        - content = ""
        - is_visible = False
        - is_loading = False
        """
        self.logger.debug("clearing_file_viewer_state")
        self._file_path.value = None
        self._content.value = ""
        self._is_visible.value = False
        self._is_loading.value = False
