"""Тесты покрытия для ProgressBar компонента.

Проверяют непокрытые строки в:
- ProgressBar
"""

from __future__ import annotations

from unittest.mock import patch

from textual.app import App
from textual.widgets import Label, Static

from codelab.client.tui.components.progress import ProgressBar, ProgressVariant


class TestProgressBarInit:
    """Тесты инициализации ProgressBar."""

    def test_init_defaults(self) -> None:
        """Инициализация со значениями по умолчанию."""
        widget = ProgressBar()
        assert widget.progress == 0.0
        assert widget.indeterminate is False
        assert widget.show_label is True
        assert widget._variant == ProgressVariant.DEFAULT
        assert widget._total is None
        assert widget._current is None
        assert widget._label_format == "{percent}%"
        assert widget.id == "progress-bar"

    def test_init_custom(self) -> None:
        """Инициализация с пользовательскими параметрами."""
        widget = ProgressBar(
            progress=0.5,
            total=10,
            current=3,
            variant=ProgressVariant.SUCCESS,
            show_label=False,
            label_format="{current}/{total}",
            id="custom-progress",
        )
        assert widget.progress == 0.5
        assert widget._total == 10
        assert widget._current == 3
        assert widget._variant == ProgressVariant.SUCCESS
        assert "-success" in widget.classes
        assert widget.show_label is False
        assert widget._label_format == "{current}/{total}"
        assert widget.id == "custom-progress"


class TestProgressBarCompose:
    """Тесты compose и свойств ProgressBar."""

    async def test_compose_and_mount(self) -> None:
        """Компонент создаёт заполнение и метку."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar()
            await pilot.app.mount(widget)

            assert isinstance(widget.fill, Static)
            assert isinstance(widget.label, Label)
            assert "0%" in str(widget.label.render())


class TestProgressBarWatchers:
    """Тесты watch_* методов ProgressBar."""

    async def test_watch_progress_updates_fill(self) -> None:
        """Изменение прогресса обновляет ширину заполнения."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar()
            await pilot.app.mount(widget)

            widget.progress = 0.5
            assert widget.fill.styles.width.value == 50

    async def test_watch_progress_clamps(self) -> None:
        """Прогресс ограничивается диапазоном [0, 1]."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar()
            await pilot.app.mount(widget)

            widget.progress = -0.5
            assert widget.fill.styles.width.value == 0

            widget.progress = 1.5
            assert widget.fill.styles.width.value == 100

    async def test_watch_progress_without_label(self) -> None:
        """При отключённой метке label не обновляется."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar(show_label=False)
            await pilot.app.mount(widget)

            with patch.object(widget.label, "update") as mock_update:
                widget.progress = 0.5
                mock_update.assert_not_called()

    async def test_watch_indeterminate_starts_animation(self) -> None:
        """Включение indeterminate запускает анимацию."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar()
            await pilot.app.mount(widget)

            widget.watch_indeterminate(True)
            assert "-indeterminate" in widget.classes
            assert widget._animation_task is not None

            widget.watch_indeterminate(False)
            assert "-indeterminate" not in widget.classes
            assert widget._animation_task is None

    async def test_watch_show_label(self) -> None:
        """Изменение show_label добавляет/убирает класс."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar()
            await pilot.app.mount(widget)

            widget.watch_show_label(False)
            assert "-no-label" in widget.classes

            widget.watch_show_label(True)
            assert "-no-label" not in widget.classes


class TestProgressBarLabel:
    """Тесты форматирования метки ProgressBar."""

    def test_format_label_default(self) -> None:
        """Формат по умолчанию содержит проценты."""
        widget = ProgressBar(progress=0.42)
        assert widget._format_label() == "42%"

    def test_format_label_with_steps(self) -> None:
        """Формат с шагами использует current и total."""
        widget = ProgressBar(
            progress=0.4,
            total=10,
            current=4,
            label_format="{current}/{total} ({percent}%)",
        )
        assert widget._format_label() == "4/10 (40%)"

    def test_format_label_default_current(self) -> None:
        """Если current не задан, вычисляется из progress."""
        widget = ProgressBar(progress=0.25, total=100)
        widget._label_format = "{current}/{total}"
        assert widget._format_label() == "25/100"


class TestProgressBarAnimation:
    """Тесты анимации ProgressBar."""

    async def test_start_animation(self) -> None:
        """_start_animation создаёт задачу анимации."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar()
            await pilot.app.mount(widget)

            widget._start_animation()
            assert widget._animation_task is not None

            widget._stop_animation()
            assert widget._animation_task is None

    async def test_start_animation_does_not_duplicate(self) -> None:
        """Повторный вызов _start_animation не создаёт вторую задачу."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar()
            await pilot.app.mount(widget)

            widget._start_animation()
            first_task = widget._animation_task
            widget._start_animation()
            assert widget._animation_task is first_task
            widget._stop_animation()


class TestProgressBarProgressMethods:
    """Тесты методов управления прогрессом."""

    async def test_set_progress(self) -> None:
        """set_progress ограничивает значение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar()
            await pilot.app.mount(widget)

            widget.set_progress(0.7)
            assert widget.progress == 0.7

            widget.set_progress(-1.0)
            assert widget.progress == 0.0

            widget.set_progress(2.0)
            assert widget.progress == 1.0

    async def test_advance(self) -> None:
        """advance увеличивает прогресс, не превышая 1."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar(progress=0.8)
            await pilot.app.mount(widget)

            widget.advance(0.3)
            assert widget.progress == 1.0

    async def test_set_steps(self) -> None:
        """set_steps устанавливает current, total и progress."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar()
            await pilot.app.mount(widget)

            widget.set_steps(3, 10)
            assert widget._current == 3
            assert widget._total == 10
            assert widget.progress == 0.3

    async def test_set_steps_zero_total(self) -> None:
        """set_steps с нулевым total устанавливает progress в 0."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar()
            await pilot.app.mount(widget)

            widget.set_steps(3, 0)
            assert widget.progress == 0.0

    async def test_reset(self) -> None:
        """reset сбрасывает прогресс."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar(progress=0.5)
            await pilot.app.mount(widget)

            widget.reset()
            assert widget.progress == 0.0
            assert widget._current is None

    async def test_complete(self) -> None:
        """complete устанавливает прогресс в 100% и отключает indeterminate."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar(indeterminate=True)
            await pilot.app.mount(widget)

            widget.complete()
            assert widget.progress == 1.0
            assert widget.indeterminate is False


class TestProgressBarVariant:
    """Тесты смены варианта ProgressBar."""

    async def test_set_variant(self) -> None:
        """set_variant меняет CSS класс варианта."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar(variant=ProgressVariant.WARNING)
            await pilot.app.mount(widget)

            widget.set_variant(ProgressVariant.ERROR)
            assert "-error" in widget.classes
            assert "-warning" not in widget.classes
            assert widget._variant == ProgressVariant.ERROR

    async def test_set_variant_default(self) -> None:
        """set_variant в DEFAULT убирает все вариантные классы."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar(variant=ProgressVariant.PRIMARY)
            await pilot.app.mount(widget)

            widget.set_variant(ProgressVariant.DEFAULT)
            assert "-primary" not in widget.classes
            assert "-success" not in widget.classes


class TestProgressBarLifecycle:
    """Тесты жизненного цикла ProgressBar."""

    async def test_on_unmount_stops_animation(self) -> None:
        """Размонтирование останавливает анимацию."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ProgressBar(indeterminate=True)
            await pilot.app.mount(widget)
            assert widget._animation_task is not None

            await widget.on_unmount()
            assert widget._animation_task is None
