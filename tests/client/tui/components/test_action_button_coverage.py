"""Тесты покрытия для ActionButton и IconButton компонентов."""

from __future__ import annotations

from unittest.mock import patch

from codelab.client.tui.components.action_button import ActionButton, IconButton


class TestActionButtonCoverage:
    """Тесты для непокрытых строк ActionButton."""

    def test_init_with_classes(self) -> None:
        """При передаче classes они добавляются к классу варианта."""
        button = ActionButton("Test", variant="primary", classes="extra-class")
        assert "primary" in button.classes
        assert "extra-class" in button.classes

    def test_button_variant_property(self) -> None:
        """button_variant возвращает текущий вариант оформления."""
        button = ActionButton("Test", variant="primary")
        assert button.button_variant == "primary"

    def test_button_variant_setter(self) -> None:
        """Установка button_variant меняет CSS-класс варианта."""
        button = ActionButton("Test", variant="primary")
        button.button_variant = "danger"

        assert button.button_variant == "danger"
        assert button.has_class("danger")
        assert not button.has_class("primary")

    def test_icon_setter(self) -> None:
        """Установка иконки обновляет отображаемый label."""
        button = ActionButton("Save", icon="💾")
        assert "💾" in str(button.label)

        button.icon = None
        assert str(button.label) == "Save"

        button.icon = "⭐"
        assert "⭐" in str(button.label)


class TestIconButtonCoverage:
    """Тесты для непокрытых строк IconButton."""

    def test_pressed_message(self) -> None:
        """Событие Pressed хранит ссылку на кнопку."""
        button = IconButton("❌")
        event = IconButton.Pressed(button)
        assert event.button is button

    def test_init_with_classes(self) -> None:
        """При передаче classes они добавляются к классу варианта."""
        button = IconButton("❌", variant="danger", classes="extra-class")
        assert "danger" in button.classes
        assert "extra-class" in button.classes

    def test_on_click_enabled(self) -> None:
        """Клик по активной кнопке отправляет событие Pressed."""
        button = IconButton("❌")
        posted: list[object] = []

        with patch.object(button, "post_message", side_effect=posted.append):
            button.on_click()

        assert len(posted) == 1
        assert isinstance(posted[0], IconButton.Pressed)

    def test_on_click_disabled(self) -> None:
        """Клик по отключенной кнопке не отправляет событие."""
        button = IconButton("❌", disabled=True)

        with patch.object(button, "post_message") as post_mock:
            button.on_click()

        post_mock.assert_not_called()
