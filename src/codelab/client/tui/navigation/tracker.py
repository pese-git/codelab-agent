"""Отслеживание активных модальных окон."""

import uuid

import structlog
from textual.screen import Screen

logger = structlog.get_logger(__name__)


class ModalWindowTracker:
    """Отслеживает активные модальные окна.

    Хранит регистрацию открытых модалей и позволяет быстро найти их по типу.
    """

    def __init__(self) -> None:
        """Инициализировать трекер модальных окон."""
        # Словарь: modal_id -> (modal_type, screen)
        self._modals: dict[str, tuple[str, Screen]] = {}
        # Словарь: modal_type -> [modal_id, ...]  для быстрого поиска по типу
        self._type_index: dict[str, list[str]] = {}

    def register_modal(
        self,
        screen: Screen,
        modal_type: str,
        modal_id: str | None = None,
    ) -> str:
        """Зарегистрировать открытое модальное окно.

        Args:
            screen: Экран модального окна
            modal_type: Тип модального окна (например, "file_viewer")
            modal_id: Уникальный ID (если None, генерируется автоматически)

        Returns:
            ID зарегистрированного модального окна
        """
        # Генерировать ID если не предоставлен
        if modal_id is None:
            modal_id = f"{modal_type}_{uuid.uuid4().hex[:8]}"

        # Зарегистрировать модаль
        self._modals[modal_id] = (modal_type, screen)

        # Добавить в индекс по типу
        if modal_type not in self._type_index:
            self._type_index[modal_type] = []
        self._type_index[modal_type].append(modal_id)

        logger.debug(
            "modal_window_registered",
            modal_id=modal_id,
            modal_type=modal_type,
            total_modals=len(self._modals),
        )

        return modal_id

    def unregister_modal(self, modal_id: str) -> None:
        """Отменить регистрацию модального окна.

        Args:
            modal_id: ID модального окна для отмены регистрации
        """
        if modal_id not in self._modals:
            logger.warning(
                "modal_window_not_found_for_unregister",
                modal_id=modal_id,
            )
            return

        modal_type, _ = self._modals[modal_id]

        # Удалить из основного словаря
        del self._modals[modal_id]

        # Удалить из индекса по типу
        if modal_type in self._type_index:
            self._type_index[modal_type].remove(modal_id)
            # Удалить тип если нет больше модалей этого типа
            if not self._type_index[modal_type]:
                del self._type_index[modal_type]

        logger.debug(
            "modal_window_unregistered",
            modal_id=modal_id,
            modal_type=modal_type,
            total_modals=len(self._modals),
        )

    def unregister_by_screen(self, screen: Screen) -> str | None:
        """Отменить регистрацию модального окна по экрану.

        Args:
            screen: Экран модального окна

        Returns:
            ID отменённого модального окна или None если не найдено
        """
        # Найти ID по экрану
        for modal_id, (_, s) in self._modals.items():
            if s is screen:
                self.unregister_modal(modal_id)
                return modal_id

        return None

    def get_modal_by_type(self, modal_type: str) -> Screen | None:
        """Найти первое (верхнее) модальное окно по типу.

        Args:
            modal_type: Тип модального окна

        Returns:
            Экран модального окна или None если не найдено
        """
        if modal_type not in self._type_index:
            return None

        # Вернуть последний (верхний) модаль этого типа
        modal_ids = self._type_index[modal_type]
        if not modal_ids:
            return None

        modal_id = modal_ids[-1]
        _, screen = self._modals[modal_id]
        return screen

    def get_all_modals_by_type(self, modal_type: str) -> list[Screen]:
        """Получить все модальные окна указанного типа.

        Args:
            modal_type: Тип модального окна

        Returns:
            Список экранов модальных окон
        """
        if modal_type not in self._type_index:
            return []

        modal_ids = self._type_index[modal_type]
        return [self._modals[modal_id][1] for modal_id in modal_ids]

    def is_modal_visible(self, modal_type: str) -> bool:
        """Проверить видимо ли модальное окно указанного типа.

        Args:
            modal_type: Тип модального окна

        Returns:
            True если модаль открыта, False если закрыта или не существует
        """
        return modal_type in self._type_index and bool(self._type_index[modal_type])

    def get_all_modals(self) -> list[tuple[str, str, Screen]]:
        """Получить все открытые модальные окна.

        Returns:
            Список кортежей (modal_id, modal_type, screen)
        """
        return [
            (modal_id, modal_type, screen)
            for modal_id, (modal_type, screen) in self._modals.items()
        ]

    def get_modal_count(self, modal_type: str | None = None) -> int:
        """Получить количество открытых модальных окон.

        Args:
            modal_type: Тип модального окна (если None, вернёт общее количество)

        Returns:
            Количество открытых модалей
        """
        if modal_type is None:
            return len(self._modals)

        return len(self._type_index.get(modal_type, []))

    def clear(self) -> None:
        """Очистить все регистрации модальных окон."""
        self._modals.clear()
        self._type_index.clear()
        logger.debug("modal_window_tracker_cleared")
