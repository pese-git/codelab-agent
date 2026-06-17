"""Тесты покрытия для MessageBubble компонентов."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from codelab.client.tui.components.message_bubble import (
    Avatar,
    MessageBubble,
    MessageContent,
    MessageRole,
)


class TestAvatarCoverage:
    """Тесты для непокрытых строк Avatar."""

    def test_role_property(self) -> None:
        """role возвращает установленную роль."""
        avatar = Avatar(MessageRole.ASSISTANT)
        assert avatar.role == MessageRole.ASSISTANT


class TestMessageContentCoverage:
    """Тесты для непокрытых строк MessageContent."""

    def test_raw_content_property(self) -> None:
        """raw_content возвращает исходный текст."""
        content = MessageContent("hello")
        assert content.raw_content == "hello"

    def test_update_content(self) -> None:
        """update_content обновляет raw_content и вызывает update."""
        content = MessageContent("initial")

        with patch.object(content, "update") as update_mock:
            content.update_content("updated")

        assert content.raw_content == "updated"
        update_mock.assert_called_once_with("updated")


class TestMessageBubbleCoverage:
    """Тесты для непокрытых строк MessageBubble."""

    def test_update_content_with_widget(self) -> None:
        """update_content обновляет контент если виджет существует."""
        bubble = MessageBubble(role=MessageRole.USER, content="hello")
        widget_mock = MagicMock()
        bubble._content_widget = widget_mock

        bubble.update_content("world")

        assert bubble.content == "world"
        widget_mock.update_content.assert_called_once_with("world")

    def test_from_dict_with_string_timestamp(self) -> None:
        """from_dict парсит timestamp из ISO-строки."""
        ts = datetime(2025, 1, 15, 12, 30, 0)
        bubble = MessageBubble.from_dict({
            "role": "assistant",
            "content": "hello",
            "timestamp": ts.isoformat(),
        })

        assert bubble.role == MessageRole.ASSISTANT
        assert bubble.content == "hello"
        assert bubble.timestamp == ts
