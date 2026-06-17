"""Тесты покрытия для toast.py.

Проверяют непокрытые строки в:
- Toast
- ToastContainer
"""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import patch

from textual.app import App

from codelab.client.tui.components.toast import (
    Toast,
    ToastContainer,
    ToastData,
    ToastType,
)


class TestToastDismissedMessage:
    """Тесты для сообщения Toast.Dismissed."""

    def test_dismissed_message_stores_id(self) -> None:
        """Dismissed сохраняет toast_id."""
        msg = Toast.Dismissed("toast-123")
        assert msg.toast_id == "toast-123"


class TestToastInit:
    """Тесты инициализации Toast."""

    def test_init_stores_data(self) -> None:
        """Toast сохраняет данные и сбрасывает задачу."""
        data = ToastData(message="test", toast_type=ToastType.INFO)
        toast = Toast(data)
        assert toast._data is data
        assert toast._dismiss_task is None


class TestToastCompose:
    """Тесты compose Toast."""

    def test_compose_without_title(self) -> None:
        """compose создаёт иконку и сообщение без заголовка."""
        data = ToastData(message="hello", toast_type=ToastType.SUCCESS)
        toast = Toast(data)
        children = list(toast.compose())

        assert toast.has_class("-success")
        assert len(children) == 2

    def test_compose_with_title(self) -> None:
        """compose создаёт иконку, заголовок и сообщение."""
        data = ToastData(message="hello", title="Title", toast_type=ToastType.WARNING)
        toast = Toast(data)
        children = list(toast.compose())

        assert toast.has_class("-warning")
        assert len(children) == 3

    def test_compose_unknown_type(self) -> None:
        """compose использует точку для неизвестного типа."""
        data = ToastData(message="hello", toast_type=ToastType.INFO)
        toast = Toast(data)
        # Подменяем иконки чтобы проверить fallback
        original_icons = Toast.ICONS.copy()
        try:
            Toast.ICONS = {}
            children = list(toast.compose())
            assert any("•" in str(child.render()) for child in children)
        finally:
            Toast.ICONS = original_icons


class TestToastMountAndDismiss:
    """Тесты жизненного цикла Toast."""

    async def test_on_mount_creates_task(self) -> None:
        """on_mount создаёт задачу авто-скрытия."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = ToastData(message="hello", duration=5.0)
            toast = Toast(data)
            await pilot.app.mount(toast)

            assert toast._dismiss_task is not None
            assert isinstance(toast._dismiss_task, asyncio.Task)
            toast._dismiss_task.cancel()

    async def test_on_mount_zero_duration_no_task(self) -> None:
        """on_mount не создаёт задачу при duration=0."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = ToastData(message="hello", duration=0.0)
            toast = Toast(data)
            await pilot.app.mount(toast)

            assert toast._dismiss_task is None

    async def test_auto_dismiss(self) -> None:
        """_auto_dismiss вызывает dismiss после задержки."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = ToastData(message="hello", duration=1.0)
            toast = Toast(data)
            await pilot.app.mount(toast)

            with patch.object(toast, "dismiss") as dismiss_mock:
                with patch("asyncio.sleep", return_value=None):
                    await toast._auto_dismiss()

            dismiss_mock.assert_called_once()

    async def test_dismiss_adds_fading_class(self) -> None:
        """dismiss добавляет класс -fading и запускает таймер."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = ToastData(message="hello", duration=0.0)
            toast = Toast(data)
            await pilot.app.mount(toast)

            called = False

            def fake_timer(delay: float, callback: object) -> None:
                nonlocal called
                called = True
                if callable(callback):
                    callback()

            with patch.object(toast, "set_timer", side_effect=fake_timer):
                toast.dismiss()

            assert toast.has_class("-fading")
            assert called is True

    async def test_remove_posts_dismissed_and_removes(self) -> None:
        """_remove отправляет сообщение и удаляет виджет."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = ToastData(message="hello", duration=0.0)
            toast = Toast(data)
            await pilot.app.mount(toast)

            with patch.object(toast, "post_message") as post_mock:
                with patch.object(toast, "remove") as remove_mock:
                    toast._remove()

            post_mock.assert_called_once()
            assert post_mock.call_args[0][0].toast_id == data.toast_id
            remove_mock.assert_called_once()

    async def test_on_click_cancels_task_and_dismisses(self) -> None:
        """Клик отменяет задачу и закрывает уведомление."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = ToastData(message="hello", duration=5.0)
            toast = Toast(data)
            await pilot.app.mount(toast)

            task = toast._dismiss_task
            with patch.object(toast, "dismiss") as dismiss_mock:
                await toast.on_click()

            with contextlib.suppress(asyncio.CancelledError):
                await task

            assert task.cancelled()
            dismiss_mock.assert_called_once()

    async def test_on_click_without_task(self) -> None:
        """Клик без задачи закрывает уведомление."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = ToastData(message="hello", duration=0.0)
            toast = Toast(data)
            await pilot.app.mount(toast)

            with patch.object(toast, "dismiss") as dismiss_mock:
                await toast.on_click()

            dismiss_mock.assert_called_once()


class TestToastContainerInit:
    """Тесты инициализации ToastContainer."""

    def test_init_defaults(self) -> None:
        """Инициализация с значениями по умолчанию."""
        container = ToastContainer()
        assert container.id == "toast-container"
        assert container._toasts == {}

    def test_init_custom_params(self) -> None:
        """Инициализация с пользовательскими параметрами."""
        container = ToastContainer(name="toasts", id="custom-toasts", classes="toast-box")
        assert container.name == "toasts"
        assert container.id == "custom-toasts"
        assert "toast-box" in container.classes


class TestToastContainerShowToast:
    """Тесты для show_toast."""

    async def test_show_toast_adds_toast(self) -> None:
        """show_toast добавляет уведомление в контейнер."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            toast_id = container.show_toast("message")

            assert toast_id in container._toasts
            assert len(container._toasts) == 1

    async def test_show_toast_with_title_and_type(self) -> None:
        """show_toast передаёт параметры в ToastData."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            toast_id = container.show_toast(
                "message",
                toast_type=ToastType.ERROR,
                duration=0.0,
                title="Ошибка",
            )

            toast = container._toasts[toast_id]
            assert toast._data.toast_type == ToastType.ERROR
            assert toast._data.title == "Ошибка"
            assert toast._data.duration == 0.0

    async def test_show_toast_max_limit(self) -> None:
        """При превышении лимита старые уведомления закрываются."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            dismiss_calls: list[str] = []

            def mock_dismiss(self_toast: Toast) -> None:
                dismiss_calls.append(self_toast._data.toast_id)
                container._toasts.pop(self_toast._data.toast_id, None)

            with patch.object(Toast, "dismiss", mock_dismiss):
                ids = []
                for _ in range(ToastContainer.MAX_TOASTS + 2):
                    toast_id = container.show_toast("msg", duration=0.0)
                    ids.append(toast_id)

            # Два oldest уведомления должны были быть закрыты
            assert len(dismiss_calls) == 2
            assert len(container._toasts) == ToastContainer.MAX_TOASTS


class TestToastContainerDismiss:
    """Тесты для dismiss и dismiss_all."""

    async def test_dismiss_toast_existing(self) -> None:
        """dismiss_toast закрывает существующее уведомление."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            toast_id = container.show_toast("message", duration=0.0)
            toast = container._toasts[toast_id]

            with patch.object(toast, "dismiss") as dismiss_mock:
                container.dismiss_toast(toast_id)

            dismiss_mock.assert_called_once()

    async def test_dismiss_toast_unknown(self) -> None:
        """dismiss_toast для неизвестного ID не падает."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            container.dismiss_toast("unknown")

    async def test_dismiss_all(self) -> None:
        """dismiss_all закрывает все уведомления."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            id1 = container.show_toast("msg1", duration=0.0)
            id2 = container.show_toast("msg2", duration=0.0)

            with patch.object(container._toasts[id1], "dismiss") as dismiss1:
                with patch.object(container._toasts[id2], "dismiss") as dismiss2:
                    container.dismiss_all()

            dismiss1.assert_called_once()
            dismiss2.assert_called_once()

    async def test_on_toast_dismissed_removes_from_dict(self) -> None:
        """on_toast_dismissed удаляет уведомление из словаря."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            toast_id = container.show_toast("message", duration=0.0)
            assert toast_id in container._toasts

            container.on_toast_dismissed(Toast.Dismissed(toast_id))
            assert toast_id not in container._toasts


class TestToastContainerConvenienceMethods:
    """Тесты удобных методов для типов уведомлений."""

    async def test_info(self) -> None:
        """info показывает информационное уведомление."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            toast_id = container.info("info msg", title="Info", duration=2.0)
            toast = container._toasts[toast_id]
            assert toast._data.toast_type == ToastType.INFO
            assert toast._data.message == "info msg"
            assert toast._data.title == "Info"
            assert toast._data.duration == 2.0

    async def test_success(self) -> None:
        """success показывает уведомление об успехе."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            toast_id = container.success("success msg", title="Success")
            toast = container._toasts[toast_id]
            assert toast._data.toast_type == ToastType.SUCCESS
            assert toast._data.duration == 3.0

    async def test_warning(self) -> None:
        """warning показывает предупреждение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            toast_id = container.warning("warning msg", title="Warning")
            toast = container._toasts[toast_id]
            assert toast._data.toast_type == ToastType.WARNING
            assert toast._data.duration == 5.0

    async def test_error(self) -> None:
        """error показывает уведомление об ошибке без авто-скрытия."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = ToastContainer()
            await pilot.app.mount(container)

            toast_id = container.error("error msg", title="Error")
            toast = container._toasts[toast_id]
            assert toast._data.toast_type == ToastType.ERROR
            assert toast._data.duration == 0.0
