"""Тесты для покрытия navigation/manager.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.screen import ModalScreen, Screen

from codelab.client.presentation.observable import Observable
from codelab.client.tui.navigation.manager import NavigationError, NavigationManager
from codelab.client.tui.navigation.queue import OperationQueueError


class _TestScreen(Screen):
    """Тестовый обычный экран."""


class _TestModalScreen(ModalScreen):
    """Тестовый модальный экран."""


class TestNavigationManagerInit:
    """Тесты инициализации NavigationManager."""

    def test_init_sets_executor(self) -> None:
        """При инициализации устанавливается executor очереди."""
        app = MagicMock()
        manager = NavigationManager(app)

        assert manager._app is app
        assert manager._queue._executor is not None
        assert manager._subscriptions == {}


class TestNavigationManagerShowScreen:
    """Тесты show_screen."""

    async def test_show_screen_pushes_and_calls_callback(self) -> None:
        """show_screen добавляет экран и вызывает callback."""
        app = MagicMock()
        app.screen_stack = []
        manager = NavigationManager(app)
        screen = _TestScreen()
        callback = MagicMock()

        await manager.show_screen(screen, callback=callback)

        app.push_screen.assert_called_once_with(screen)
        callback.assert_called_once_with(screen)

    async def test_show_modal_registers_tracker(self) -> None:
        """Модальный экран регистрируется в трекере."""
        app = MagicMock()
        app.screen_stack = []
        manager = NavigationManager(app)
        screen = _TestModalScreen()

        await manager.show_screen(screen, modal=True)

        assert manager.is_modal_visible("_TestModalScreen") is True
        assert manager.get_modal_by_type("_TestModalScreen") is screen

    async def test_show_screen_queue_error(self) -> None:
        """Ошибка очереди при показе экрана превращается в NavigationError."""
        app = MagicMock()
        app.screen_stack = []
        manager = NavigationManager(app)
        screen = _TestScreen()

        with patch.object(
            manager._queue, "enqueue", new_callable=AsyncMock
        ) as enqueue_mock:
            enqueue_mock.side_effect = OperationQueueError("fail")

            with pytest.raises(NavigationError):
                await manager.show_screen(screen)


class TestNavigationManagerHideScreen:
    """Тесты hide_screen."""

    async def test_hide_screen_by_object_dismisses_modal(self) -> None:
        """Скрытие модального экрана по объекту вызывает dismiss."""
        app = MagicMock()
        app.screen_stack = []
        manager = NavigationManager(app)
        screen = _TestModalScreen()
        screen.dismiss = MagicMock()

        await manager.show_screen(screen, modal=True)
        app.screen_stack = [screen]
        callback = MagicMock()

        await manager.hide_screen(screen, result="ok", callback=callback)

        screen.dismiss.assert_called_once_with("ok")
        callback.assert_called_once()
        assert manager.is_modal_visible("_TestModalScreen") is False

    async def test_hide_screen_by_string_pops_top(self) -> None:
        """Скрытие по строке использует верхний экран стека."""
        app = MagicMock()
        app.screen_stack = []
        manager = NavigationManager(app)
        screen = _TestScreen()

        await manager.show_screen(screen)
        app.screen_stack = [screen]

        await manager.hide_screen("ignored-id")

        app.pop_screen.assert_called_once()

    async def test_hide_screen_queue_error(self) -> None:
        """Ошибка очереди при скрытии экрана превращается в NavigationError."""
        app = MagicMock()
        manager = NavigationManager(app)

        with patch.object(
            manager._queue, "enqueue", new_callable=AsyncMock
        ) as enqueue_mock:
            enqueue_mock.side_effect = OperationQueueError("fail")

            with pytest.raises(NavigationError):
                await manager.hide_screen("screen-id")


class TestNavigationManagerHideTopScreen:
    """Тесты hide_top_screen."""

    async def test_hide_top_screen_pops(self) -> None:
        """hide_top_screen убирает верхний экран."""
        app = MagicMock()
        app.screen_stack = []
        manager = NavigationManager(app)
        screen = _TestScreen()

        await manager.show_screen(screen)
        app.screen_stack = [screen]

        await manager.hide_top_screen(result="done")

        app.pop_screen.assert_called_once()

    async def test_hide_top_screen_empty_stack(self) -> None:
        """Пустой стек при hide_top_screen вызывает NavigationError."""
        app = MagicMock()
        app.screen_stack = []
        manager = NavigationManager(app)

        with pytest.raises(NavigationError):
            await manager.hide_top_screen()

    async def test_hide_top_screen_queue_error(self) -> None:
        """Ошибка очереди при hide_top_screen превращается в NavigationError."""
        app = MagicMock()
        manager = NavigationManager(app)

        with patch.object(
            manager._queue, "enqueue", new_callable=AsyncMock
        ) as enqueue_mock:
            enqueue_mock.side_effect = OperationQueueError("fail")

            with pytest.raises(NavigationError):
                await manager.hide_top_screen()


class TestNavigationManagerScreenStack:
    """Тесты работы со стеком экранов."""

    def test_get_screen_stack_depth(self) -> None:
        """Глубина стека возвращает длину screen_stack."""
        app = MagicMock()
        app.screen_stack = [MagicMock(), MagicMock()]
        manager = NavigationManager(app)

        assert manager.get_screen_stack_depth() == 2


class TestNavigationManagerReset:
    """Тесты reset."""

    async def test_reset_closes_all_modals(self) -> None:
        """reset закрывает все модальные окна и очищает трекер."""
        app = MagicMock()
        app.screen_stack = []
        manager = NavigationManager(app)
        modal1 = _TestModalScreen()
        modal1.dismiss = MagicMock()
        modal2 = _TestModalScreen()
        modal2.dismiss = MagicMock()

        await manager.show_screen(modal1, modal=True)
        await manager.show_screen(modal2, modal=True)

        await manager.reset()

        modal1.dismiss.assert_called_once_with(None)
        modal2.dismiss.assert_called_once_with(None)
        assert manager._tracker.get_modal_count() == 0

    async def test_reset_continues_on_close_error(self) -> None:
        """reset продолжает работу при ошибке закрытия модала."""
        app = MagicMock()
        app.screen_stack = []
        manager = NavigationManager(app)
        modal = _TestModalScreen()
        modal.dismiss = MagicMock(side_effect=RuntimeError("dismiss fail"))

        await manager.show_screen(modal, modal=True)

        await manager.reset()

        assert manager._tracker.get_modal_count() == 0

    async def test_reset_queue_error(self) -> None:
        """Ошибка очереди при reset превращается в NavigationError."""
        app = MagicMock()
        manager = NavigationManager(app)

        with patch.object(
            manager._queue, "enqueue", new_callable=AsyncMock
        ) as enqueue_mock:
            enqueue_mock.side_effect = OperationQueueError("fail")

            with pytest.raises(NavigationError):
                await manager.reset()


class TestNavigationManagerSubscribe:
    """Тесты subscribe_to_view_model."""

    async def test_subscribe_show_and_hide(self) -> None:
        """Подписка синхронизирует видимость и вызывает callback."""
        app = MagicMock()
        manager = NavigationManager(app)
        vm = MagicMock()
        vm.is_visible = Observable(False)
        on_show = MagicMock()
        on_hide = MagicMock()
        modal = MagicMock()

        unsubscribe = manager.subscribe_to_view_model(
            vm, "permission", on_show=on_show, on_hide=on_hide
        )

        with patch.object(manager, "get_modal_by_type", return_value=modal):
            with patch.object(manager, "hide_screen", new_callable=AsyncMock):
                vm.is_visible.value = True
                on_show.assert_called_once()

                vm.is_visible.value = False
                await asyncio.sleep(0)
                manager.hide_screen.assert_awaited_once_with(modal)
                on_hide.assert_called_once()

        unsubscribe()
        assert "view_model_permission" not in manager._subscriptions

    async def test_subscribe_non_observable(self) -> None:
        """Для ViewModel без is_visible возвращается пустая функция."""
        app = MagicMock()
        manager = NavigationManager(app)
        vm = MagicMock()
        del vm.is_visible

        unsubscribe = manager.subscribe_to_view_model(vm, "permission")

        assert unsubscribe() is None


class TestNavigationManagerDispose:
    """Тесты dispose."""

    def test_dispose_clears_resources(self) -> None:
        """dispose отписывает ViewModel и очищает трекер с очередью."""
        app = MagicMock()
        manager = NavigationManager(app)
        vm = MagicMock()
        vm.is_visible.subscribe = MagicMock(return_value=MagicMock())
        vm.is_visible.unsubscribe = MagicMock()

        manager.subscribe_to_view_model(vm, "permission")
        manager._tracker.register_modal(MagicMock(), "permission")

        manager.dispose()

        vm.is_visible.unsubscribe.assert_called_once()
        assert manager._subscriptions == {}
        assert manager._tracker.get_modal_count() == 0
        assert manager._queue.is_empty() is True


class TestNavigationManagerExecuteOperation:
    """Тесты внутреннего выполнения операций."""

    async def test_execute_unknown_operation(self) -> None:
        """Неизвестный тип операции вызывает NavigationError."""
        app = MagicMock()
        manager = NavigationManager(app)
        operation = MagicMock()
        operation.operation_type = MagicMock()
        operation.operation_type.value = "unknown"

        with pytest.raises(NavigationError):
            await manager._execute_operation(operation)

    async def test_handle_show_screen_error_unregisters_modal(self) -> None:
        """При ошибке показа модаль снимается с регистрации."""
        app = MagicMock()
        app.screen_stack = []
        app.push_screen = MagicMock(side_effect=RuntimeError("push fail"))
        manager = NavigationManager(app)
        screen = _TestModalScreen()

        with pytest.raises(NavigationError):
            await manager.show_screen(screen, modal=True)

        assert manager.is_modal_visible("_TestModalScreen") is False

    async def test_handle_hide_screen_pop_error(self) -> None:
        """Ошибка при скрытии обычного экрана превращается в NavigationError."""
        app = MagicMock()
        app.screen_stack = []
        manager = NavigationManager(app)
        screen = _TestScreen()

        await manager.show_screen(screen)
        app.screen_stack = [screen]
        app.pop_screen = MagicMock(side_effect=RuntimeError("pop fail"))

        with pytest.raises(NavigationError):
            await manager.hide_screen(screen)
