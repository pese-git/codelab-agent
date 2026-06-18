"""Тесты покрытия для spinner.py."""

from __future__ import annotations

import asyncio

from textual.app import App

from codelab.client.tui.components.spinner import (
    LoadingIndicator,
    Spinner,
    SpinnerSize,
    SpinnerVariant,
)


class TestSpinnerSizeAndVariant:
    """Тесты для enum."""

    def test_spinner_size_values(self) -> None:
        """SpinnerSize имеет ожидаемые значения."""
        assert SpinnerSize.SMALL.value == "sm"
        assert SpinnerSize.MEDIUM.value == "md"
        assert SpinnerSize.LARGE.value == "lg"

    def test_spinner_variant_values(self) -> None:
        """SpinnerVariant имеет ожидаемые значения."""
        assert SpinnerVariant.DOTS.value == "dots"
        assert SpinnerVariant.LINE.value == "line"
        assert SpinnerVariant.CIRCLE.value == "circle"
        assert SpinnerVariant.ARROW.value == "arrow"
        assert SpinnerVariant.PULSE.value == "pulse"


class TestSpinner:
    """Тесты для Spinner."""

    async def test_init_defaults(self) -> None:
        """Инициализация с параметрами по умолчанию."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner()
            await pilot.app.mount(spinner)
            assert spinner.id == "spinner"
            assert spinner._spinner_size == SpinnerSize.MEDIUM
            assert spinner._variant == SpinnerVariant.DOTS
            assert spinner.text == ""
            assert spinner.spinning is True
            assert spinner.has_class("-md")
            spinner._stop_animation()

    async def test_init_custom(self) -> None:
        """Инициализация с параметрами."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(
                text="Loading",
                size=SpinnerSize.LARGE,
                variant=SpinnerVariant.LINE,
                spinning=False,
                id="custom",
            )
            await pilot.app.mount(spinner)
            assert spinner.id == "custom"
            assert spinner.text == "Loading"
            assert spinner._spinner_size == SpinnerSize.LARGE
            assert spinner._variant == SpinnerVariant.LINE
            assert spinner.spinning is False
            assert spinner.has_class("-lg")

    async def test_compose(self) -> None:
        """compose создает метки анимации и текста."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(text="Wait")
            await pilot.app.mount(spinner)
            assert spinner.animation_label
            assert spinner.text_label
            assert "Wait" in str(spinner.text_label.render())

    async def test_watch_text(self) -> None:
        """watch_text обновляет текстовую метку."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner()
            await pilot.app.mount(spinner)
            spinner.text = "New"
            assert "New" in str(spinner.text_label.render())

    async def test_watch_spinning_starts_animation(self) -> None:
        """watch_spinning запускает анимацию."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(spinning=False)
            await pilot.app.mount(spinner)
            assert spinner._animation_task is None
            spinner.spinning = True
            assert spinner._animation_task is not None
            spinner._stop_animation()

    async def test_watch_spinning_stops_animation(self) -> None:
        """watch_spinning останавливает анимацию."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(spinning=True)
            await pilot.app.mount(spinner)
            assert spinner._animation_task is not None
            spinner.spinning = False
            assert spinner._animation_task is None

    async def test_start(self) -> None:
        """start запускает спиннер и убирает hidden."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(spinning=False)
            await pilot.app.mount(spinner)
            spinner.add_class("-hidden")
            spinner.start()
            assert spinner.spinning is True
            assert not spinner.has_class("-hidden")

    async def test_stop(self) -> None:
        """stop останавливает спиннер."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(spinning=True)
            await pilot.app.mount(spinner)
            spinner.stop()
            assert spinner.spinning is False
            assert spinner._animation_task is None

    async def test_hide(self) -> None:
        """hide останавливает и скрывает спиннер."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(spinning=True)
            await pilot.app.mount(spinner)
            spinner.hide()
            assert spinner.spinning is False
            assert spinner.has_class("-hidden")

    async def test_show(self) -> None:
        """show показывает и запускает спиннер."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(spinning=False)
            await pilot.app.mount(spinner)
            spinner.add_class("-hidden")
            spinner.show()
            assert spinner.spinning is True
            assert not spinner.has_class("-hidden")

    async def test_set_text(self) -> None:
        """set_text обновляет текст."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(spinning=False)
            await pilot.app.mount(spinner)
            spinner.set_text("New text")
            assert spinner.text == "New text"

    async def test_set_variant(self) -> None:
        """set_variant меняет вариант анимации."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(variant=SpinnerVariant.DOTS, spinning=True)
            await pilot.app.mount(spinner)
            spinner.set_variant(SpinnerVariant.LINE)
            assert spinner._variant == SpinnerVariant.LINE
            assert spinner._frame_index == 0
            spinner._stop_animation()

    async def test_set_variant_while_stopped(self) -> None:
        """set_variant работает когда анимация остановлена."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(spinning=False)
            await pilot.app.mount(spinner)
            spinner.set_variant(SpinnerVariant.CIRCLE)
            assert spinner._variant == SpinnerVariant.CIRCLE
            assert spinner._animation_task is None

    async def test_on_unmount(self) -> None:
        """on_unmount останавливает анимацию."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(spinning=True)
            await pilot.app.mount(spinner)
            assert spinner._animation_task is not None
            await spinner.on_unmount()
            assert spinner._animation_task is None

    async def test_animation_advances_frame(self) -> None:
        """Анимация меняет кадры."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            spinner = Spinner(variant=SpinnerVariant.LINE, size=SpinnerSize.SMALL)
            await pilot.app.mount(spinner)
            assert spinner._animation_task is not None
            initial_index = spinner._frame_index
            await asyncio.sleep(0.15)
            assert spinner._frame_index != initial_index
            spinner._stop_animation()


class TestLoadingIndicator:
    """Тесты для LoadingIndicator."""

    def test_init_defaults(self) -> None:
        """Инициализация по умолчанию."""
        indicator = LoadingIndicator()
        assert indicator.id == "loading-indicator"
        assert indicator.visible is True

    def test_init_custom(self) -> None:
        """Инициализация с параметрами."""
        indicator = LoadingIndicator(
            text="Wait",
            size=SpinnerSize.LARGE,
            variant=SpinnerVariant.LINE,
            visible=False,
            id="custom",
        )
        assert indicator.id == "custom"
        assert indicator._text == "Wait"
        assert indicator.visible is False

    async def test_compose(self) -> None:
        """compose создает Spinner."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            indicator = LoadingIndicator()
            await pilot.app.mount(indicator)
            assert indicator.spinner is not None

    async def test_watch_visible(self) -> None:
        """watch_visible управляет видимостью и спиннером."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            indicator = LoadingIndicator(visible=True)
            await pilot.app.mount(indicator)
            indicator.visible = False
            assert indicator.has_class("-hidden")
            assert indicator.spinner.spinning is False

    async def test_show(self) -> None:
        """show показывает индикатор и меняет текст."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            indicator = LoadingIndicator(visible=False)
            await pilot.app.mount(indicator)
            indicator.show("New text")
            assert indicator.visible is True
            assert indicator.spinner.text == "New text"

    async def test_hide(self) -> None:
        """hide скрывает индикатор."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            indicator = LoadingIndicator(visible=True)
            await pilot.app.mount(indicator)
            indicator.hide()
            assert indicator.visible is False

    async def test_set_text(self) -> None:
        """set_text обновляет текст спиннера."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            indicator = LoadingIndicator()
            await pilot.app.mount(indicator)
            indicator.set_text("Updated")
            assert indicator.spinner.text == "Updated"

    def test_set_text_spinner_missing(self) -> None:
        """set_text сохраняет текст если спиннер недоступен."""
        indicator = LoadingIndicator()
        indicator.set_text("Saved")
        assert indicator._text == "Saved"
