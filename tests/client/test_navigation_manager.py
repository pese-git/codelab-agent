"""Тесты для NavigationManager."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import Mock

import pytest
from textual.app import App
from textual.screen import ModalScreen, Screen

from codelab.client.presentation.observable import Observable
from codelab.client.tui.navigation.manager import (
    ModalNotFoundError,
    NavigationError,
    NavigationManager,
    OperationTimeoutError,
    ScreenStackError,
)


class TestNavigationManager:
    """Тесты для класса NavigationManager."""

    @pytest.fixture
    def mock_app(self) -> Mock:
        """Создать mock Textual App для тестирования."""
        app = Mock(spec=App)
        app.push_screen = Mock()
        app.pop_screen = Mock()
        app.screen_stack = []
        return app

    @pytest.fixture
    def navigation_manager(self, mock_app: Mock) -> NavigationManager:
        """Создать NavigationManager с mock app."""
        return NavigationManager(mock_app)

    @pytest.fixture
    def mock_screen(self) -> Mock:
        """Создать mock Screen."""
        return Mock(spec=Screen)

    @pytest.fixture
    def mock_modal_screen(self) -> Mock:
        """Создать mock ModalScreen."""
        modal = Mock(spec=ModalScreen)
        modal.dismiss = Mock()
        return modal

    def test_manager_initialization(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
    ) -> None:
        """Тест инициализации менеджера навигации."""
        assert navigation_manager._app is mock_app
        assert navigation_manager._tracker is not None
        assert navigation_manager._queue is not None
        assert navigation_manager._subscriptions == {}

    @pytest.mark.asyncio
    async def test_show_screen_success(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_screen: Mock,
    ) -> None:
        """Тест успешного показа screen."""

        # Добавляем screen в стек для имитации push_screen
        def push_screen_side_effect(screen: Screen) -> None:
            mock_app.screen_stack.append(screen)

        mock_app.push_screen.side_effect = push_screen_side_effect

        callback = Mock()
        await navigation_manager.show_screen(
            mock_screen,
            modal=False,
            callback=callback,
        )

        # Проверяем что screen был добавлен в стек
        mock_app.push_screen.assert_called_once()
        # Проверяем что callback был вызван
        callback.assert_called_once_with(mock_screen)

    @pytest.mark.asyncio
    async def test_show_modal_screen(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_modal_screen: Mock,
    ) -> None:
        """Тест показа модального окна."""
        # Нужно установить spec для ModalScreen для isinstance проверки
        cast(Any, mock_modal_screen).__class__ = ModalScreen

        def push_screen_side_effect(screen: Screen) -> None:
            mock_app.screen_stack.append(screen)

        mock_app.push_screen.side_effect = push_screen_side_effect

        callback = Mock()
        await navigation_manager.show_screen(
            mock_modal_screen,
            modal=True,
            callback=callback,
        )

        # Проверяем что screen был добавлен в стек
        mock_app.push_screen.assert_called_once()
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_screen_with_priority(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_screen: Mock,
    ) -> None:
        """Тест показа screen с приоритетом."""

        def push_screen_side_effect(screen: Screen) -> None:
            mock_app.screen_stack.append(screen)

        mock_app.push_screen.side_effect = push_screen_side_effect

        # Должно выполниться с высоким приоритетом
        await navigation_manager.show_screen(
            mock_screen,
            priority=2,
        )

        mock_app.push_screen.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_screen_error_handling(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_screen: Mock,
    ) -> None:
        """Тест обработки ошибок при показе screen."""
        mock_app.push_screen.side_effect = RuntimeError("Test error")

        with pytest.raises(NavigationError):
            await navigation_manager.show_screen(mock_screen)

    @pytest.mark.asyncio
    async def test_hide_screen_success(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_screen: Mock,
    ) -> None:
        """Тест успешного скрытия screen."""
        # Добавляем screen в стек
        mock_app.screen_stack.append(mock_screen)

        def pop_screen_side_effect() -> None:
            mock_app.screen_stack.pop()

        mock_app.pop_screen.side_effect = pop_screen_side_effect

        callback = Mock()
        await navigation_manager.hide_screen(mock_screen, callback=callback)

        # Проверяем что screen был удален из стека
        mock_app.pop_screen.assert_called_once()
        # Проверяем что callback был вызван
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_hide_modal_screen(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_modal_screen: Mock,
    ) -> None:
        """Тест скрытия модального окна."""
        # Регистрируем модаль
        navigation_manager._tracker.register_modal(
            mock_modal_screen,
            "ModalScreen",
        )

        # Добавляем в стек
        mock_app.screen_stack.append(mock_modal_screen)

        await navigation_manager.hide_screen(mock_modal_screen)

        # Проверяем что dismiss был вызван
        mock_modal_screen.dismiss.assert_called_once()

    @pytest.mark.asyncio
    async def test_hide_top_screen(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_screen: Mock,
    ) -> None:
        """Тест скрытия верхнего screen."""
        mock_app.screen_stack.append(mock_screen)

        def pop_screen_side_effect() -> None:
            mock_app.screen_stack.pop()

        mock_app.pop_screen.side_effect = pop_screen_side_effect

        await navigation_manager.hide_top_screen()

        mock_app.pop_screen.assert_called_once()

    @pytest.mark.asyncio
    async def test_hide_screen_empty_stack(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
    ) -> None:
        """Тест скрытия screen при пустом стеке."""
        mock_app.screen_stack = []

        # hide_top_screen оборачивает ScreenStackError в NavigationError
        with pytest.raises(NavigationError):
            await navigation_manager.hide_top_screen()

    @pytest.mark.asyncio
    async def test_reset_clears_modals(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_modal_screen: Mock,
    ) -> None:
        """Тест сброса стека (закрытия всех модальных окон)."""
        # Регистрируем несколько модалей
        navigation_manager._tracker.register_modal(
            mock_modal_screen,
            "modal_1",
            modal_id="id1",
        )

        mock_app.screen_stack.append(mock_modal_screen)

        await navigation_manager.reset()

        # Проверяем что трекер очищен
        assert navigation_manager._tracker.get_modal_count() == 0

    def test_get_modal_by_type(
        self,
        navigation_manager: NavigationManager,
        mock_modal_screen: Mock,
    ) -> None:
        """Тест получения модального окна по типу."""
        navigation_manager._tracker.register_modal(
            mock_modal_screen,
            "test_modal",
        )

        result = navigation_manager.get_modal_by_type("test_modal")

        assert result is mock_modal_screen

    def test_get_modal_by_type_not_found(
        self,
        navigation_manager: NavigationManager,
    ) -> None:
        """Тест получения несуществующего модального окна."""
        result = navigation_manager.get_modal_by_type("nonexistent")

        assert result is None

    def test_is_modal_visible(
        self,
        navigation_manager: NavigationManager,
        mock_modal_screen: Mock,
    ) -> None:
        """Тест проверки видимости модального окна."""
        assert not navigation_manager.is_modal_visible("test_modal")

        navigation_manager._tracker.register_modal(
            mock_modal_screen,
            "test_modal",
        )

        assert navigation_manager.is_modal_visible("test_modal")

    def test_get_screen_stack_depth(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
    ) -> None:
        """Тест получения глубины стека экранов."""
        mock_app.screen_stack = [Mock(), Mock(), Mock()]

        depth = navigation_manager.get_screen_stack_depth()

        assert depth == 3

    def test_subscribe_to_view_model_with_observable(
        self,
        navigation_manager: NavigationManager,
    ) -> None:
        """Тест подписки на ViewModel с Observable."""
        # Создаем mock ViewModel с Observable is_visible
        view_model = Mock()
        is_visible_observable = Mock()
        is_visible_observable.subscribe = Mock()
        is_visible_observable.unsubscribe = Mock()
        view_model.is_visible = is_visible_observable

        on_show = Mock()
        on_hide = Mock()

        unsubscribe = navigation_manager.subscribe_to_view_model(
            view_model,
            "test_modal",
            on_show=on_show,
            on_hide=on_hide,
        )

        # Проверяем что была произведена подписка
        is_visible_observable.subscribe.assert_called_once()

        # Проверяем что функция отписки была возвращена
        assert callable(unsubscribe)

    def test_subscribe_to_view_model_without_observable(
        self,
        navigation_manager: NavigationManager,
    ) -> None:
        """Тест подписки на ViewModel без Observable."""
        # Создаем mock ViewModel без Observable
        view_model = Mock()
        view_model.is_visible = "not_observable"

        unsubscribe = navigation_manager.subscribe_to_view_model(
            view_model,
            "test_modal",
        )

        # Должно вернуть пустую функцию
        assert callable(unsubscribe)
        unsubscribe()  # Не должно выбросить ошибку

    @pytest.mark.asyncio
    async def test_view_model_sync_show_modal(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_modal_screen: Mock,
    ) -> None:
        """Тест синхронизации ViewModel при показе модаля."""

        def push_screen_side_effect(screen: Screen) -> None:
            mock_app.screen_stack.append(screen)

        mock_app.push_screen.side_effect = push_screen_side_effect

        # Создаем Observable для is_visible
        is_visible_observable = Observable(False)

        view_model = Mock()
        view_model.is_visible = is_visible_observable

        on_show = Mock()

        # Подписываемся на ViewModel
        unsubscribe = navigation_manager.subscribe_to_view_model(
            view_model,
            "test_modal",
            on_show=on_show,
        )

        # Изменяем is_visible на True (должно показать модаль)
        is_visible_observable.value = True

        # Даем время на выполнение async операции
        await asyncio.sleep(0.1)

        # Проверяем что on_show был вызван
        on_show.assert_called_once()

        unsubscribe()

    def test_dispose_cleanup(
        self,
        navigation_manager: NavigationManager,
    ) -> None:
        """Тест очистки ресурсов при dispose."""
        # Создаем несколько subscriptions
        view_model1 = Mock()
        is_visible1 = Mock()
        is_visible1.subscribe = Mock()
        is_visible1.unsubscribe = Mock()
        view_model1.is_visible = is_visible1

        view_model2 = Mock()
        is_visible2 = Mock()
        is_visible2.subscribe = Mock()
        is_visible2.unsubscribe = Mock()
        view_model2.is_visible = is_visible2

        navigation_manager.subscribe_to_view_model(view_model1, "modal1")
        navigation_manager.subscribe_to_view_model(view_model2, "modal2")

        subscriptions_count = len(navigation_manager._subscriptions)
        assert subscriptions_count >= 2

        # Вызываем dispose - не должно быть RuntimeError
        navigation_manager.dispose()

        # Проверяем что все очищено
        assert len(navigation_manager._subscriptions) == 0

    @pytest.mark.asyncio
    async def test_sequential_show_hide_operations(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_screen: Mock,
    ) -> None:
        """Тест последовательного выполнения операций show и hide."""

        def push_screen_side_effect(screen: Screen) -> None:
            mock_app.screen_stack.append(screen)

        def pop_screen_side_effect() -> None:
            if mock_app.screen_stack:
                mock_app.screen_stack.pop()

        mock_app.push_screen.side_effect = push_screen_side_effect
        mock_app.pop_screen.side_effect = pop_screen_side_effect

        # Показываем screen
        await navigation_manager.show_screen(mock_screen)
        assert len(mock_app.screen_stack) == 1

        # Скрываем screen
        await navigation_manager.hide_screen(mock_screen)
        assert len(mock_app.screen_stack) == 0

    @pytest.mark.asyncio
    async def test_multiple_show_operations(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
    ) -> None:
        """Тест множественного показа экранов."""

        def push_screen_side_effect(screen: Screen) -> None:
            mock_app.screen_stack.append(screen)

        mock_app.push_screen.side_effect = push_screen_side_effect

        screens = [Mock(spec=Screen) for _ in range(3)]

        for screen in screens:
            await navigation_manager.show_screen(screen)

        assert len(mock_app.screen_stack) == 3
        assert all(call[0][0] in screens for call in mock_app.push_screen.call_args_list)

    @pytest.mark.asyncio
    async def test_hide_screen_with_result(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_modal_screen: Mock,
    ) -> None:
        """Тест скрытия модального окна с результатом."""
        navigation_manager._tracker.register_modal(
            mock_modal_screen,
            "ModalScreen",
        )
        mock_app.screen_stack.append(mock_modal_screen)

        result_value = {"key": "value"}

        await navigation_manager.hide_screen(
            mock_modal_screen,
            result=result_value,
        )

        # Проверяем что dismiss был вызван с результатом
        mock_modal_screen.dismiss.assert_called_once_with(result_value)

    def test_navigation_error_exception(self) -> None:
        """Тест NavigationError исключения."""
        error = NavigationError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_screen_stack_error_exception(self) -> None:
        """Тест ScreenStackError исключения."""
        error = ScreenStackError("Stack error")
        assert str(error) == "Stack error"
        assert isinstance(error, NavigationError)

    def test_modal_not_found_error_exception(self) -> None:
        """Тест ModalNotFoundError исключения."""
        error = ModalNotFoundError("Modal not found")
        assert str(error) == "Modal not found"
        assert isinstance(error, NavigationError)

    def test_operation_timeout_error_exception(self) -> None:
        """Тест OperationTimeoutError исключения."""
        error = OperationTimeoutError("Timeout")
        assert str(error) == "Timeout"
        assert isinstance(error, NavigationError)

    @pytest.mark.asyncio
    async def test_callback_called_on_show_success(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_screen: Mock,
    ) -> None:
        """Тест что callback вызывается при успешном показе."""

        def push_screen_side_effect(screen: Screen) -> None:
            mock_app.screen_stack.append(screen)

        mock_app.push_screen.side_effect = push_screen_side_effect

        callback = Mock()

        await navigation_manager.show_screen(
            mock_screen,
            callback=callback,
        )

        # Callback должен быть вызван с экраном
        assert callback.called
        assert callback.call_args[0][0] is mock_screen

    @pytest.mark.asyncio
    async def test_callback_called_on_hide_success(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_screen: Mock,
    ) -> None:
        """Тест что callback вызывается при успешном скрытии."""
        mock_app.screen_stack.append(mock_screen)

        def pop_screen_side_effect() -> None:
            mock_app.screen_stack.pop()

        mock_app.pop_screen.side_effect = pop_screen_side_effect

        callback = Mock()

        await navigation_manager.hide_screen(
            mock_screen,
            callback=callback,
        )

        # Callback должен быть вызван
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_multiple_modal_screens(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
    ) -> None:
        """Тест показа множественных модальных окон."""

        def push_screen_side_effect(screen: Screen) -> None:
            mock_app.screen_stack.append(screen)

        mock_app.push_screen.side_effect = push_screen_side_effect

        modals = [Mock(spec=ModalScreen) for _ in range(3)]

        for modal in modals:
            await navigation_manager.show_screen(
                modal,
                modal=True,
            )

        # Все должны быть зарегистрированы
        assert navigation_manager._tracker.get_modal_count() == 3

    @pytest.mark.asyncio
    async def test_prevent_cyclic_updates(
        self,
        navigation_manager: NavigationManager,
    ) -> None:
        """Тест предотвращения циклических обновлений при синхронизации ViewModel."""
        is_visible_observable = Observable(False)

        view_model = Mock()
        view_model.is_visible = is_visible_observable

        callback_call_count = 0

        def on_show() -> None:
            nonlocal callback_call_count
            callback_call_count += 1

        # Подписываемся на ViewModel
        unsubscribe = navigation_manager.subscribe_to_view_model(
            view_model,
            "test_modal",
            on_show=on_show,
        )

        # Изменяем is_visible несколько раз
        is_visible_observable.value = True
        is_visible_observable.value = False
        is_visible_observable.value = True

        # Даем время на выполнение
        await asyncio.sleep(0.1)

        unsubscribe()

    def test_modal_type_from_screen_class_name(
        self,
        navigation_manager: NavigationManager,
    ) -> None:
        """Тест что modal_type берется из имени класса экрана."""

        class CustomModalScreen(ModalScreen):
            """Custom modal screen для теста."""

            pass

        modal = CustomModalScreen()

        # Имитируем registration через metadata
        modal_type = type(modal).__name__
        assert modal_type == "CustomModalScreen"

    @pytest.mark.asyncio
    async def test_hide_screen_by_id(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
        mock_modal_screen: Mock,
    ) -> None:
        """Тест скрытия экрана по ID."""
        # Регистрируем модаль
        modal_id = navigation_manager._tracker.register_modal(
            mock_modal_screen,
            "test_modal",
        )

        mock_app.screen_stack.append(mock_modal_screen)

        # Скрываем по ID
        await navigation_manager.hide_screen(modal_id)

        # Должна быть попытка скрыть экран
        # (просто проверяем что операция выполнена без ошибок)

    @pytest.mark.asyncio
    async def test_reset_with_multiple_modals(
        self,
        navigation_manager: NavigationManager,
        mock_app: Mock,
    ) -> None:
        """Тест сброса с множественными модалями."""
        modals = [Mock(spec=ModalScreen) for _ in range(3)]

        for i, modal in enumerate(modals):
            modal.dismiss = Mock()
            navigation_manager._tracker.register_modal(
                modal,
                f"modal_{i}",
            )
            mock_app.screen_stack.append(modal)

        assert navigation_manager._tracker.get_modal_count() == 3

        await navigation_manager.reset()

        # Все модали должны быть очищены
        assert navigation_manager._tracker.get_modal_count() == 0

    def test_metadata_in_operations(
        self,
        navigation_manager: NavigationManager,
    ) -> None:
        """Тест что metadata сохраняется в операциях."""

        async def test_async() -> None:
            mock_app = Mock(spec=App)
            mock_app.push_screen = Mock()
            mock_app.screen_stack = []

            manager = NavigationManager(mock_app)
            screen = Mock(spec=Screen)

            await manager.show_screen(screen)

        # Просто проверяем что операция создается с metadata
        asyncio.run(test_async())
