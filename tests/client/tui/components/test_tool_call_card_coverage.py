"""Тесты покрытия для tool_call_card.py."""

from __future__ import annotations

from textual.app import App
from textual.widgets import Collapsible, Static

from codelab.client.tui.components.permission_badge import PermissionBadge
from codelab.client.tui.components.tool_call_card import (
    MCP_TOOL_ICON,
    STATUS_ICONS,
    TOOL_ICONS,
    ToolCallCard,
)


class TestToolCallCardConstants:
    """Тесты для констант ToolCallCard."""

    def test_tool_icons_contain_defaults(self) -> None:
        """TOOL_ICONS содержит ожидаемые иконки."""
        assert "read_file" in TOOL_ICONS
        assert "default" in TOOL_ICONS

    def test_status_icons_contain_all_statuses(self) -> None:
        """STATUS_ICONS содержит все статусы."""
        for status in ("pending", "running", "success", "error", "cancelled"):
            assert status in STATUS_ICONS

    def test_mcp_tool_icon(self) -> None:
        """MCP иконка определена."""
        assert MCP_TOOL_ICON


class TestToolCallCard:
    """Тесты для ToolCallCard."""

    def test_init_defaults(self) -> None:
        """Инициализация с параметрами по умолчанию."""
        card = ToolCallCard("call_1", "read_file")
        assert card.tool_call_id == "call_1"
        assert card.tool_name == "read_file"
        assert card.status == "pending"
        assert card.result is None
        assert card.error is None
        assert card.id == "tool-call_1"

    def test_init_custom(self) -> None:
        """Инициализация с параметрами."""
        card = ToolCallCard(
            "call_1",
            "write_file",
            parameters={"path": "/tmp"},
            status="running",
            result="done",
            error="fail",
            classes="extra",
        )
        assert card.status == "running"
        assert card.result == "done"
        assert card.error == "fail"
        assert card.has_class("running")
        assert card.has_class("extra")

    async def test_compose_known_tool(self) -> None:
        """compose создает структуру для известного инструмента."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            card = ToolCallCard("call_1", "read_file", parameters={"path": "/tmp"})
            await pilot.app.mount(card)
            assert card.query_one("#tool-icon", Static)
            assert card.query_one("#tool-name", Static)
            assert card.query_one("#tool-status", PermissionBadge)
            assert card.query_one(Collapsible)
            assert card.query_one("#tool-result", Static)
            assert card.query_one("#tool-error", Static)

    async def test_compose_mcp_tool(self) -> None:
        """compose использует MCP иконку."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            card = ToolCallCard("call_1", "mcp:server/tool")
            await pilot.app.mount(card)
            icon = card.query_one("#tool-icon", Static)
            assert MCP_TOOL_ICON in str(icon.render())

    async def test_compose_default_icon(self) -> None:
        """compose использует дефолтную иконку."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            card = ToolCallCard("call_1", "unknown_tool")
            await pilot.app.mount(card)
            icon = card.query_one("#tool-icon", Static)
            assert TOOL_ICONS["default"] in str(icon.render())

    async def test_status_setter(self) -> None:
        """Сеттер status обновляет классы и badge."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            card = ToolCallCard("call_1", "read_file", status="pending")
            await pilot.app.mount(card)
            card.status = "success"
            assert card.status == "success"
            assert card.has_class("success")
            assert not card.has_class("pending")
            badge = card.query_one("#tool-status", PermissionBadge)
            assert badge.status == "granted"

            card.status = "error"
            badge = card.query_one("#tool-status", PermissionBadge)
            assert badge.status == "denied"

    def test_status_setter_not_mounted(self) -> None:
        """Сеттер status не падает без монтирования."""
        card = ToolCallCard("call_1", "read_file", status="pending")
        card.status = "success"
        assert card.status == "success"

    async def test_result_setter(self) -> None:
        """Сеттер result обновляет виджет результата."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            card = ToolCallCard("call_1", "read_file")
            await pilot.app.mount(card)
            card.result = "output"
            result_widget = card.query_one("#tool-result", Static)
            assert result_widget.display is True
            assert "output" in str(result_widget.render())

            card.result = None
            assert result_widget.display is False

    def test_result_setter_not_mounted(self) -> None:
        """Сеттер result не падает без монтирования."""
        card = ToolCallCard("call_1", "read_file")
        card.result = "output"
        assert card.result == "output"

    async def test_error_setter(self) -> None:
        """Сеттер error обновляет виджет ошибки."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            card = ToolCallCard("call_1", "read_file")
            await pilot.app.mount(card)
            card.error = "boom"
            error_widget = card.query_one("#tool-error", Static)
            assert error_widget.display is True
            assert "boom" in str(error_widget.render())

            card.error = None
            assert error_widget.display is False

    def test_error_setter_not_mounted(self) -> None:
        """Сеттер error не падает без монтирования."""
        card = ToolCallCard("call_1", "read_file")
        card.error = "boom"
        assert card.error == "boom"

    def test_format_parameters(self) -> None:
        """_format_parameters форматирует параметры."""
        card = ToolCallCard("call_1", "read_file", parameters={"path": "/tmp", "x": 1})
        text = card._format_parameters()
        assert "path: /tmp" in text
        assert "x: 1" in text

    def test_format_parameters_long_value(self) -> None:
        """_format_parameters укорачивает длинные значения."""
        card = ToolCallCard("call_1", "read_file", parameters={"x": "a" * 100})
        text = card._format_parameters()
        assert "..." in text

    def test_truncate(self) -> None:
        """_truncate укорачивает длинный текст."""
        card = ToolCallCard("call_1", "read_file")
        assert card._truncate("abc", 10) == "abc"
        assert card._truncate("a" * 100, 10) == "a" * 7 + "..."
        assert card._truncate(None, 10) == ""
        assert card._truncate("", 10) == ""

    async def test_on_click_posts_selected(self) -> None:
        """Клик отправляет Selected."""
        from unittest.mock import patch

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            card = ToolCallCard("call_1", "read_file")
            await pilot.app.mount(card)
            with patch.object(card, "post_message") as post_mock:
                card.on_click()
            post_mock.assert_called_once()
            event = post_mock.call_args[0][0]
            assert isinstance(event, ToolCallCard.Selected)
            assert event.card is card
            assert event.tool_call_id == "call_1"

    async def test_toggle_expanded(self) -> None:
        """toggle_expanded переключает collapsible."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            card = ToolCallCard("call_1", "read_file", parameters={"x": 1})
            await pilot.app.mount(card)
            collapsible = card.query_one(Collapsible)
            initial = collapsible.collapsed
            card.toggle_expanded()
            assert collapsible.collapsed is not initial

    def test_toggle_expanded_not_mounted(self) -> None:
        """toggle_expanded не падает без монтирования."""
        card = ToolCallCard("call_1", "read_file", parameters={"x": 1})
        card.toggle_expanded()
        assert card._expanded is True
