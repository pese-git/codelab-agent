"""Дополнительные тесты покрытия для StateManager.

Покрывает ранее непокрытые ветки:
- _extract_text_from_content_blocks
"""

from __future__ import annotations

import pytest

from codelab.server.protocol.handlers.state_manager import (
    StateManager,
    _extract_text_from_content_blocks,
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


class TestHistorySeams:
    """Тесты делегирования истории в носитель состояния."""

    def test_add_user_message_delegates_to_seam(
        self,
        state_manager: StateManager,
        session: SessionState,
    ) -> None:
        """Запись истории идёт через history-seam носителя состояния (фаза B)."""
        state_manager.add_user_message(session, [{"type": "text", "text": "test"}])

        assert len(session.history) == 1
        entry = session.history[0]
        assert isinstance(entry, dict)
        assert entry["role"] == "user"
        assert entry["content"] == [{"type": "text", "text": "test"}]
        assert "timestamp" in entry
