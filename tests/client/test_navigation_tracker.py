"""Тесты для ModalWindowTracker."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from textual.screen import Screen

from codelab.client.tui.navigation.tracker import ModalWindowTracker


class TestModalWindowTracker:
    """Тесты для класса ModalWindowTracker."""

    @pytest.fixture
    def tracker(self) -> ModalWindowTracker:
        """Создать экземпляр трекера модальных окон."""
        return ModalWindowTracker()

    @pytest.fixture
    def mock_screen(self) -> Screen:
        """Создать mock Screen."""
        return Mock(spec=Screen)

    def test_tracker_initialization(self, tracker: ModalWindowTracker) -> None:
        """Тест инициализации пустого трекера."""
        assert tracker.get_modal_count() == 0
        assert tracker.get_all_modals() == []

    def test_register_single_modal(
        self,
        tracker: ModalWindowTracker,
        mock_screen: Screen,
    ) -> None:
        """Тест регистрации одного модального окна."""
        modal_id = tracker.register_modal(mock_screen, "test_modal", modal_id="explicit_id")
        
        assert modal_id == "explicit_id"
        assert tracker.get_modal_count() == 1
        assert tracker.is_modal_visible("test_modal")

    def test_register_modal_auto_id(
        self,
        tracker: ModalWindowTracker,
        mock_screen: Screen,
    ) -> None:
        """Тест автоматической генерации ID для модального окна."""
        modal_id = tracker.register_modal(mock_screen, "test_modal")
        
        # ID должен содержать тип и быть уникальным
        assert modal_id.startswith("test_modal_")
        assert len(modal_id) > len("test_modal_")

    def test_register_modal_explicit_id(
        self,
        tracker: ModalWindowTracker,
        mock_screen: Screen,
    ) -> None:
        """Тест регистрации модального окна с явным ID."""
        explicit_id = "my_custom_id"
        modal_id = tracker.register_modal(
            mock_screen,
            "test_modal",
            modal_id=explicit_id,
        )
        
        assert modal_id == explicit_id

    def test_unregister_modal(
        self,
        tracker: ModalWindowTracker,
        mock_screen: Screen,
    ) -> None:
        """Тест отмены регистрации модального окна."""
        modal_id = tracker.register_modal(mock_screen, "test_modal")
        assert tracker.get_modal_count() == 1
        
        tracker.unregister_modal(modal_id)
        assert tracker.get_modal_count() == 0
        assert not tracker.is_modal_visible("test_modal")

    def test_unregister_nonexistent_modal(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест отмены регистрации несуществующего модального окна."""
        # Должно пройти без ошибок
        tracker.unregister_modal("nonexistent_id")
        assert tracker.get_modal_count() == 0

    def test_unregister_by_screen(
        self,
        tracker: ModalWindowTracker,
        mock_screen: Screen,
    ) -> None:
        """Тест отмены регистрации по экрану."""
        modal_id = tracker.register_modal(mock_screen, "test_modal")
        
        result_id = tracker.unregister_by_screen(mock_screen)
        
        assert result_id == modal_id
        assert tracker.get_modal_count() == 0

    def test_unregister_by_nonexistent_screen(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест отмены регистрации несуществующего экрана."""
        result_id = tracker.unregister_by_screen(Mock(spec=Screen))
        
        assert result_id is None
        assert tracker.get_modal_count() == 0

    def test_get_modal_by_type(
        self,
        tracker: ModalWindowTracker,
        mock_screen: Screen,
    ) -> None:
        """Тест получения модального окна по типу."""
        tracker.register_modal(mock_screen, "test_modal")
        
        result_screen = tracker.get_modal_by_type("test_modal")
        
        assert result_screen is mock_screen

    def test_get_modal_by_type_nonexistent(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест получения несуществующего модального окна по типу."""
        result = tracker.get_modal_by_type("nonexistent")
        
        assert result is None

    def test_get_modal_by_type_returns_last(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест что get_modal_by_type возвращает последнее (верхнее) модальное окно."""
        screen1 = Mock(spec=Screen)
        screen2 = Mock(spec=Screen)
        screen3 = Mock(spec=Screen)
        
        tracker.register_modal(screen1, "test_modal", modal_id="id1")
        tracker.register_modal(screen2, "test_modal", modal_id="id2")
        tracker.register_modal(screen3, "test_modal", modal_id="id3")
        
        # Должно вернуть последнее добавленное
        result = tracker.get_modal_by_type("test_modal")
        assert result is screen3

    def test_get_all_modals_by_type(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест получения всех модальных окон указанного типа."""
        screen1 = Mock(spec=Screen)
        screen2 = Mock(spec=Screen)
        screen3 = Mock(spec=Screen)
        
        tracker.register_modal(screen1, "test_modal", modal_id="id1")
        tracker.register_modal(screen2, "test_modal", modal_id="id2")
        tracker.register_modal(screen3, "other_modal", modal_id="id3")
        
        result = tracker.get_all_modals_by_type("test_modal")
        
        assert len(result) == 2
        assert screen1 in result
        assert screen2 in result
        assert screen3 not in result

    def test_get_all_modals_by_type_empty(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест получения пустого списка для несуществующего типа."""
        result = tracker.get_all_modals_by_type("nonexistent")
        
        assert result == []

    def test_is_modal_visible(
        self,
        tracker: ModalWindowTracker,
        mock_screen: Screen,
    ) -> None:
        """Тест проверки видимости модального окна."""
        assert not tracker.is_modal_visible("test_modal")
        
        tracker.register_modal(mock_screen, "test_modal")
        
        assert tracker.is_modal_visible("test_modal")

    def test_is_modal_visible_after_unregister(
        self,
        tracker: ModalWindowTracker,
        mock_screen: Screen,
    ) -> None:
        """Тест видимости модального окна после отмены регистрации."""
        modal_id = tracker.register_modal(mock_screen, "test_modal")
        assert tracker.is_modal_visible("test_modal")
        
        tracker.unregister_modal(modal_id)
        
        assert not tracker.is_modal_visible("test_modal")

    def test_get_all_modals(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест получения всех открытых модальных окон."""
        screen1 = Mock(spec=Screen)
        screen2 = Mock(spec=Screen)
        screen3 = Mock(spec=Screen)
        
        tracker.register_modal(screen1, "modal_1", modal_id="id1")
        tracker.register_modal(screen2, "modal_2", modal_id="id2")
        tracker.register_modal(screen3, "modal_3", modal_id="id3")
        
        all_modals = tracker.get_all_modals()
        
        assert len(all_modals) == 3
        assert ("id1", "modal_1", screen1) in all_modals
        assert ("id2", "modal_2", screen2) in all_modals
        assert ("id3", "modal_3", screen3) in all_modals

    def test_get_all_modals_empty(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест получения пустого списка всех модалей."""
        all_modals = tracker.get_all_modals()
        
        assert all_modals == []

    def test_get_modal_count_total(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест получения общего количества модальных окон."""
        screen1 = Mock(spec=Screen)
        screen2 = Mock(spec=Screen)
        screen3 = Mock(spec=Screen)
        
        tracker.register_modal(screen1, "modal_1")
        tracker.register_modal(screen2, "modal_2")
        tracker.register_modal(screen3, "modal_3")
        
        assert tracker.get_modal_count() == 3

    def test_get_modal_count_by_type(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест получения количества модальных окон по типу."""
        screen1 = Mock(spec=Screen)
        screen2 = Mock(spec=Screen)
        screen3 = Mock(spec=Screen)
        
        tracker.register_modal(screen1, "test_modal", modal_id="id1")
        tracker.register_modal(screen2, "test_modal", modal_id="id2")
        tracker.register_modal(screen3, "other_modal", modal_id="id3")
        
        assert tracker.get_modal_count("test_modal") == 2
        assert tracker.get_modal_count("other_modal") == 1
        assert tracker.get_modal_count("nonexistent") == 0

    def test_clear_all_modals(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест очистки всех модальных окон."""
        screen1 = Mock(spec=Screen)
        screen2 = Mock(spec=Screen)
        screen3 = Mock(spec=Screen)
        
        tracker.register_modal(screen1, "modal_1")
        tracker.register_modal(screen2, "modal_2")
        tracker.register_modal(screen3, "modal_3")
        
        assert tracker.get_modal_count() == 3
        
        tracker.clear()
        
        assert tracker.get_modal_count() == 0
        assert tracker.get_all_modals() == []

    def test_register_with_same_id_overwrites(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест что регистрация с одинаковым ID перезаписывает старый modal."""
        screen1 = Mock(spec=Screen)
        screen2 = Mock(spec=Screen)
        
        tracker.register_modal(screen1, "modal_type", modal_id="same_id")
        tracker.register_modal(screen2, "modal_type", modal_id="same_id")
        
        # Должно быть только одно модальное окно
        assert tracker.get_modal_count() == 1
        
        # Должно быть новое значение
        result = tracker.get_modal_by_type("modal_type")
        assert result is screen2

    def test_multiple_types_independence(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест независимости разных типов модальных окон."""
        screen1 = Mock(spec=Screen)
        screen2 = Mock(spec=Screen)
        
        tracker.register_modal(screen1, "type_a", modal_id="id1")
        tracker.register_modal(screen2, "type_b", modal_id="id2")
        
        # Удаляем type_a
        tracker.unregister_modal("id1")
        
        # type_b должен остаться
        assert not tracker.is_modal_visible("type_a")
        assert tracker.is_modal_visible("type_b")
        assert tracker.get_modal_count() == 1

    def test_register_multiple_same_type(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест регистрации множественных модальных окон одного типа."""
        screens = [Mock(spec=Screen) for _ in range(5)]
        
        ids = []
        for screen in screens:
            modal_id = tracker.register_modal(screen, "same_type")
            ids.append(modal_id)
        
        # Все должны быть уникальными
        assert len(set(ids)) == 5
        
        # Все должны быть видимыми
        assert tracker.get_modal_count("same_type") == 5
        
        # get_all_modals_by_type должен вернуть все
        all_screens = tracker.get_all_modals_by_type("same_type")
        assert len(all_screens) == 5

    def test_unregister_middle_modal(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест удаления модального окна из середины списка."""
        screen1 = Mock(spec=Screen)
        screen2 = Mock(spec=Screen)
        screen3 = Mock(spec=Screen)
        
        tracker.register_modal(screen1, "type", modal_id="id1")
        id2 = tracker.register_modal(screen2, "type", modal_id="id2")
        tracker.register_modal(screen3, "type", modal_id="id3")
        
        # Удаляем среднее
        tracker.unregister_modal(id2)
        
        # Остальные должны оставаться
        all_screens = tracker.get_all_modals_by_type("type")
        assert len(all_screens) == 2
        assert screen1 in all_screens
        assert screen3 in all_screens
        assert screen2 not in all_screens

    def test_type_index_cleanup_after_unregister(
        self,
        tracker: ModalWindowTracker,
        mock_screen: Screen,
    ) -> None:
        """Тест что индекс типов очищается после удаления последнего модаля."""
        modal_id = tracker.register_modal(mock_screen, "test_modal")
        assert tracker.is_modal_visible("test_modal")
        
        # Удаляем единственное модальное окно
        tracker.unregister_modal(modal_id)
        
        # После удаления последнего окна тип должен исчезнуть из индекса
        assert not tracker.is_modal_visible("test_modal")
        assert tracker.get_all_modals_by_type("test_modal") == []

    def test_get_modal_count_none_vs_all(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест что get_modal_count без аргумента считает все модали."""
        screen1 = Mock(spec=Screen)
        screen2 = Mock(spec=Screen)
        screen3 = Mock(spec=Screen)
        
        tracker.register_modal(screen1, "type_a", modal_id="id1")
        tracker.register_modal(screen2, "type_b", modal_id="id2")
        tracker.register_modal(screen3, "type_c", modal_id="id3")
        
        # Без аргумента должно вернуть общее количество
        total = tracker.get_modal_count(None)
        assert total == 3

    def test_screen_identity(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест что трекер сохраняет идентичность объектов Screen."""
        screen = Mock(spec=Screen)
        
        tracker.register_modal(screen, "test_modal")
        
        retrieved = tracker.get_modal_by_type("test_modal")
        
        # Должна быть точно та же ссылка
        assert retrieved is screen

    def test_concurrent_registration(
        self,
        tracker: ModalWindowTracker,
    ) -> None:
        """Тест регистрации из разных потоков (синхронный код)."""
        # Поскольку это синхронный класс, тестируем просто быстрые регистрации
        screens = [Mock(spec=Screen) for _ in range(10)]
        
        for i, screen in enumerate(screens):
            tracker.register_modal(screen, f"type_{i % 3}")
        
        assert tracker.get_modal_count() == 10
        
        # Проверяем что группировка по типам работает правильно
        type_0_count = tracker.get_modal_count("type_0")
        type_1_count = tracker.get_modal_count("type_1")
        type_2_count = tracker.get_modal_count("type_2")
        
        assert type_0_count + type_1_count + type_2_count == 10
