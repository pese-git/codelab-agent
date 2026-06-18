"""ViewModel для управления файловой системой.

Отвечает за управление состоянием FileTree компонента:
- Корневой путь файлового дерева
- Выбранный путь в дереве
- Статус загрузки
"""

from pathlib import Path
from typing import Any

from codelab.client.presentation.base_view_model import BaseViewModel
from codelab.client.presentation.observable import Observable


class FileSystemViewModel(BaseViewModel):
    """ViewModel для отображения файлового дерева.
    
    Управляет состоянием компонента FileTree:
    - root_path: корневой путь для отображения в дереве
    - selected_path: текущий выбранный файл/папка в дереве
    - is_loading: флаг загрузки дерева файлов
    
    Все изменения делаются через ViewModel для обеспечения
    реактивности и контролируемого изменения состояния.
    
    Пример использования:
        >>> vm = FileSystemViewModel()
        >>> vm.set_root(Path("/home/user/project"))
        >>> vm.selected_path.subscribe(lambda p: print(f"Selected: {p}"))
        >>> vm.select_path(Path("/home/user/project/src/main.py"))
    """
    
    def __init__(
        self,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        """Инициализировать FileSystemViewModel.
        
        Args:
            event_bus: EventBus для публикации/подписки на события
            logger: Logger для структурированного логирования
        """
        super().__init__(event_bus, logger)
        # Корневой путь файлового дерева
        self._root_path: Observable[Path | None] = Observable(None)
        # Выбранный путь в дереве
        self._selected_path: Observable[Path | None] = Observable(None)
        # Статус загрузки дерева
        self._is_loading: Observable[bool] = Observable(False)
    
    @property
    def root_path(self) -> Observable:
        """Корневой путь файлового дерева.
        
        Returns:
            Observable со значением корневого пути или None если не установлен.
        """
        return self._root_path
    
    @property
    def selected_path(self) -> Observable:
        """Выбранный путь в дереве.
        
        Returns:
            Observable со значением выбранного пути или None если ничего не выбрано.
        """
        return self._selected_path
    
    @property
    def is_loading(self) -> Observable:
        """Загружается ли дерево.
        
        Returns:
            Observable с флагом загрузки дерева.
        """
        return self._is_loading
    
    def set_root(self, path: Path) -> None:
        """Установить корневой путь.
        
        Обновляет корневой путь файлового дерева и уведомляет
        все подписанные observers об изменении.
        
        Args:
            path: Новый корневой путь (объект Path).
        """
        self.logger.debug("setting_root_path", path=str(path))
        self._root_path.value = path
    
    def select_path(self, path: Path | None) -> None:
        """Выбрать путь в дереве.
        
        Обновляет выбранный путь и уведомляет всех observers.
        
        Args:
            path: Выбранный путь (Path) или None для очистки выбора.
        """
        if path is not None:
            self.logger.debug("selecting_path", path=str(path))
        else:
            self.logger.debug("clearing_selection")
        self._selected_path.value = path
    
    def set_loading(self, loading: bool) -> None:
        """Установить статус загрузки.
        
        Обновляет флаг загрузки дерева файлов и уведомляет observers.
        Используется при асинхронной загрузке структуры дерева.
        
        Args:
            loading: True если дерево загружается, False иначе.
        """
        self.logger.debug("setting_loading", loading=loading)
        self._is_loading.value = loading
    
    def clear(self) -> None:
        """Очистить состояние.
        
        Сбрасывает все свойства ViewModel в исходное состояние:
        - root_path -> None
        - selected_path -> None
        - is_loading -> False
        
        Используется при закрытии сессии или сброса UI.
        """
        self.logger.debug("clearing_filesystem_view_model")
        self._root_path.value = None
        self._selected_path.value = None
        self._is_loading.value = False
