"""ViewModel для управления запросами разрешений.

Отвечает за:
- Управление состоянием модального окна разрешений
- Хранение типа разрешения, ресурса и сообщения
- Управление видимостью модального окна
"""

from __future__ import annotations

from typing import Any

from codelab.client.presentation.base_view_model import BaseViewModel
from codelab.client.presentation.observable import Observable


class PermissionViewModel(BaseViewModel):
    """ViewModel для отображения запросов разрешений.
    
    Управляет состоянием модального окна PermissionModal:
    - permission_type: тип запрашиваемого разрешения
    - resource: ресурс для которого запрашивается разрешение
    - message: сообщение с описанием запроса
    - is_visible: видимо ли модальное окно
    
    Все изменения делаются через методы ViewModel для обеспечения
    реактивности и контролируемого изменения состояния.
    
    Пример использования:
        >>> vm = PermissionViewModel()
        >>> vm.is_visible.subscribe(lambda v: print(f"Видим: {v}"))
        >>> 
        >>> # Показать запрос разрешения
        >>> vm.show_request("file_read", "/home/user/file.txt", "Read access needed")
        >>> 
        >>> # Скрыть
        >>> vm.hide()
    """
    
    def __init__(
        self,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        """Инициализировать PermissionViewModel.
        
        Args:
            event_bus: EventBus для публикации/подписки на события
            logger: Logger для структурированного логирования
        """
        super().__init__(event_bus, logger)
        # Тип запрашиваемого разрешения
        self._permission_type: Observable[str] = Observable("")
        # Ресурс для которого запрашивается разрешение
        self._resource: Observable[str] = Observable("")
        # Сообщение с описанием запроса
        self._message: Observable[str] = Observable("")
        # Видимо ли модальное окно
        self._is_visible: Observable[bool] = Observable(False)
    
    @property
    def permission_type(self) -> Observable:
        """Тип запрашиваемого разрешения.
        
        Returns:
            Observable со строкой типа разрешения.
        """
        return self._permission_type
    
    @property
    def resource(self) -> Observable:
        """Ресурс для которого запрашивается разрешение.
        
        Returns:
            Observable со строкой пути или названия ресурса.
        """
        return self._resource
    
    @property
    def message(self) -> Observable:
        """Сообщение с описанием запроса.
        
        Returns:
            Observable со строкой сообщения.
        """
        return self._message
    
    @property
    def is_visible(self) -> Observable:
        """Видимо ли модальное окно.
        
        Returns:
            Observable с булевым значением видимости.
        """
        return self._is_visible
    
    def show_request(
        self,
        permission_type: str,
        resource: str,
        message: str = "",
    ) -> None:
        """Показать запрос разрешения.
        
        Устанавливает состояние ViewModel для отображения запроса разрешения.
        Все подписчики будут уведомлены об изменениях через Observable.
        
        Args:
            permission_type: Тип запрашиваемого разрешения (например, "file_read", "execute")
            resource: Ресурс для которого запрашивается разрешение (путь к файлу, команда и т.д.)
            message: Опциональное сообщение с дополнительной информацией о запросе
        """
        self._permission_type.value = permission_type
        self._resource.value = resource
        self._message.value = message
        self._is_visible.value = True
        self.logger.debug(
            "permission_request_shown",
            permission_type=permission_type,
            resource=resource,
        )
    
    def hide(self) -> None:
        """Скрыть модальное окно.
        
        Устанавливает видимость в False, но сохраняет предыдущие значения
        для возможной повторной активации.
        """
        self._is_visible.value = False
        self.logger.debug("permission_modal_hidden")
    
    def clear(self) -> None:
        """Очистить состояние.
        
        Сбрасывает все значения в исходное состояние.
        Используется для полной очистки ViewModel после обработки запроса.
        """
        self._permission_type.value = ""
        self._resource.value = ""
        self._message.value = ""
        self._is_visible.value = False
        self.logger.debug("permission_view_model_cleared")
