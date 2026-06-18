"""Дополнительные тесты покрытия для StateManager.

Покрывает ранее непокрытые ветки:
- _sanitize_history_entry (невалидные записи)
- _extract_text_from_content_blocks
- add_event с различными входными данными.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from codelab.server.protocol.handlers.state_manager import (
    StateManager,
    _extract_text_from_content_blocks,
    _sanitize_history_entry,
)
from codelab.server.protocol.state import SessionState


@pytest.fixture
def state_manager() -> StateManager:
    """Создает экземпляр StateManager для тестов."""
    return StateManager()


@pytest.fixture
def session() -> SessionState:
    """Создает экземпляр SessionState для тестов."""
    return SessionState(
        session_id="sess_1",
        cwd="/tmp",
        mcp_servers=[],
    )


class TestSanitizeHistoryEntry:
    """Тесты валидации записей истории."""

    def test_sanitize_rejects_non_dict_entry(self) -> None:
        """Не-dict запись отклоняется с логированием предупреждения."""
        assert _sanitize_history_entry("not a dict") is None

    def test_sanitize_rejects_missing_role(self) -> None:
        """Запись без поля role отклоняется."""
        entry = {"content": "some content"}
        assert _sanitize_history_entry(entry) is None

    def test_sanitize_rejects_missing_content_fields(self) -> None:
        """Запись без content/text/message отклоняется."""
        entry = {"role": "user"}
        assert _sanitize_history_entry(entry) is None

    def test_sanitize_accepts_text_entry(self) -> None:
        """Запись с полем text принимается."""
        entry = {"role": "assistant", "text": "hello"}
        assert _sanitize_history_entry(entry) == entry


class TestExtractTextFromContentBlocks:
    """Тесты извлечения текста из content blocks."""

    def test_returns_empty_for_non_list(self) -> None:
        """При передаче не списка возвращается пустая строка."""
        assert _extract_text_from_content_blocks("not a list") == ""

    def test_returns_empty_when_no_text_block(self) -> None:
        """Возвращается пустая строка, если текстового блока нет."""
        blocks = [{"type": "image", "url": "http://example.com"}]
        assert _extract_text_from_content_blocks(blocks) == ""

    def test_returns_first_text_block(self) -> None:
        """Возвращается текст первого текстового блока."""
        blocks = [
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ]
        assert _extract_text_from_content_blocks(blocks) == "first"

    def test_skips_non_string_text(self) -> None:
        """Блоки с нестроковым text игнорируются."""
        blocks = [
            {"type": "text", "text": 123},
            {"type": "text", "text": "valid"},
        ]
        assert _extract_text_from_content_blocks(blocks) == "valid"


class TestAddEvent:
    """Тесты добавления событий в events_history."""

    def test_add_event_with_timestamp(
        self,
        state_manager: StateManager,
        session: SessionState,
    ) -> None:
        """Событие с timestamp добавляется без изменений."""
        event = {"type": "test", "timestamp": "2026-01-01T00:00:00Z"}
        state_manager.add_event(session, event)

        assert len(session.events_history) == 1
        assert session.events_history[0]["timestamp"] == "2026-01-01T00:00:00Z"

    def test_add_event_without_timestamp(
        self,
        state_manager: StateManager,
        session: SessionState,
    ) -> None:
        """К событию без timestamp добавляется текущее время."""
        event = {"type": "test"}
        state_manager.add_event(session, event)

        assert len(session.events_history) == 1
        assert "timestamp" in session.events_history[0]

    def test_add_event_with_sanitized_history(
        self,
        state_manager: StateManager,
        session: SessionState,
    ) -> None:
        """Сообщение не добавляется в историю, если санитайзер вернул None."""
        with patch(
            "codelab.server.protocol.handlers.state_manager._sanitize_history_entry",
            return_value=None,
        ):
            state_manager.add_user_message(session, [{"type": "text", "text": "test"}])
            assert len(session.history) == 0
