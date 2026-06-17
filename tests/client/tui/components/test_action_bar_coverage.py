"""Тесты покрытия для ActionBar компонента."""

from __future__ import annotations

from unittest.mock import patch

from textual.app import App

from codelab.client.tui.components.action_bar import ActionBar


class TestActionBarCoverage:
    """Тесты для непокрытых строк action_bar.py."""

    def test_init_with_classes(self) -> None:
        """При передаче classes они добавляются к CSS-классам выравнивания."""
        bar = ActionBar(classes="extra-class")
        assert "center" in bar.classes
        assert "extra-class" in bar.classes

    async def test_set_action_disabled(self) -> None:
        """set_action_disabled меняет состояние кнопки."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = ActionBar()
            await pilot.app.mount(bar)
            button = bar.add_action("Test", action_id="test")
            assert not button.disabled

            bar.set_action_disabled("test", True)
            assert button.disabled is True

            bar.set_action_disabled("test", False)
            assert button.disabled is False

    async def test_remove_action(self) -> None:
        """remove_action удаляет кнопку из панели."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = ActionBar()
            await pilot.app.mount(bar)
            button = bar.add_action("Test", action_id="test")

            with patch.object(button, "remove") as remove_mock:
                bar.remove_action("test")

            assert bar.get_action("test") is None
            remove_mock.assert_called_once()

    async def test_clear_actions(self) -> None:
        """clear_actions удаляет все кнопки из панели."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = ActionBar()
            await pilot.app.mount(bar)
            button_a = bar.add_action("A", action_id="a")
            button_b = bar.add_action("B", action_id="b")

            with (
                patch.object(button_a, "remove") as remove_a_mock,
                patch.object(button_b, "remove") as remove_b_mock,
            ):
                bar.clear_actions()

            assert bar.get_action("a") is None
            assert bar.get_action("b") is None
            remove_a_mock.assert_called_once()
            remove_b_mock.assert_called_once()
