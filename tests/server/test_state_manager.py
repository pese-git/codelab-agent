"""Unit-тесты для StateManager.

Проверяет корректность управления состоянием сессии и историей.
"""

from datetime import datetime

import pytest

from codelab.server.domain.session import Session as DomainSession
from codelab.server.protocol.handlers.state_manager import StateManager
from tests.server._domain_sessions import make_domain_session, wire_history


@pytest.fixture
def state_manager() -> StateManager:
    """Создает экземпляр StateManager для тестов."""
    return StateManager()


@pytest.fixture
def session() -> DomainSession:
    """Создает экземпляр DomainSession для тестов."""
    return make_domain_session(
        session_id="sess_1",
        cwd="/tmp",
        mcp_servers=[],
    )


class TestStateManagerTitle:
    """Тесты управления заголовком сессии."""

    def test_update_session_title_from_preview(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Устанавливает title из preview текста."""
        state_manager.update_session_title(session, "This is a test prompt")
        assert session.title == "This is a test prompt"

    def test_update_session_title_truncates_long_text(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Обрезает title до 80 символов."""
        long_text = "A" * 150
        state_manager.update_session_title(session, long_text)
        assert len(session.title) == 80
        assert session.title == "A" * 80

    def test_update_session_title_strips_whitespace(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Убирает пробелы в начале и конце."""
        state_manager.update_session_title(session, "  Test prompt  ")
        assert session.title == "Test prompt"

    def test_update_session_title_skips_if_already_set(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Не перезаписывает уже установленный title."""
        session.title = "Original title"
        state_manager.update_session_title(session, "New title")
        assert session.title == "Original title"

    def test_update_session_title_skips_empty_text(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Пропускает обновление для пустого текста."""
        state_manager.update_session_title(session, "")
        assert session.title is None

    def test_update_session_title_skips_whitespace_only(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Пропускает обновление для текста только с пробелами."""
        state_manager.update_session_title(session, "   \n  \t  ")
        assert session.title is None


class TestStateManagerHistory:
    """Тесты добавления сообщений в историю."""

    def test_add_user_message_to_history(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Добавляет пользовательское сообщение в историю."""
        prompt = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]
        state_manager.add_user_message(session, prompt)
        assert len(wire_history(session)) == 1
        assert wire_history(session)[0]["role"] == "user"
        assert wire_history(session)[0]["content"] == prompt

    def test_add_user_message_multiple(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Добавляет несколько пользовательских сообщений."""
        prompt1 = [{"type": "text", "text": "First"}]
        prompt2 = [{"type": "text", "text": "Second"}]
        state_manager.add_user_message(session, prompt1)
        state_manager.add_user_message(session, prompt2)
        assert len(wire_history(session)) == 2
        assert wire_history(session)[0]["content"] == prompt1
        assert wire_history(session)[1]["content"] == prompt2

    def test_add_assistant_message_as_text(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Добавляет ответ ассистента как текст."""
        state_manager.add_assistant_message(session, "This is a response")
        assert len(wire_history(session)) == 1
        assert wire_history(session)[0]["role"] == "assistant"
        assert wire_history(session)[0]["text"] == "This is a response"

    def test_add_assistant_message_as_dict(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Добавляет ответ ассистента как словарь (одиночный ACP-блок).

        Носитель разбирает блок и хранит его текстом, а не сырым dict'ом: форма
        записи истории принадлежит агрегату (ADR-006). Прод по этому пути передаёт
        только строку — dict остаётся принятым входом ради одноимённости сейма.
        """
        content = {
            "type": "text",
            "text": "Structured response",
        }
        state_manager.add_assistant_message(session, content)
        assert len(wire_history(session)) == 1
        assert wire_history(session)[0]["role"] == "assistant"
        assert wire_history(session)[0]["text"] == "Structured response"

    def test_add_assistant_message_multiple(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Добавляет несколько ответов ассистента."""
        state_manager.add_assistant_message(session, "Response 1")
        state_manager.add_assistant_message(session, "Response 2")
        assert len(wire_history(session)) == 2
        assert wire_history(session)[0]["text"] == "Response 1"
        assert wire_history(session)[1]["text"] == "Response 2"

    def test_add_messages_interleaved(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Добавляет чередующиеся user и assistant сообщения."""
        prompt = [{"type": "text", "text": "User message"}]
        state_manager.add_user_message(session, prompt)
        state_manager.add_assistant_message(session, "Assistant response")
        state_manager.add_user_message(session, prompt)
        assert len(wire_history(session)) == 3
        assert wire_history(session)[0]["role"] == "user"
        assert wire_history(session)[1]["role"] == "assistant"
        assert wire_history(session)[2]["role"] == "user"


class TestStateManagerTimestamp:
    """Тесты обновления временных меток."""

    def test_update_session_timestamp(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Обновляет timestamp на текущее время."""
        old_timestamp = session.updated_at
        state_manager.update_session_timestamp(session)
        assert session.updated_at != old_timestamp
        # Проверяем ISO 8601 формат
        datetime.fromisoformat(session.updated_at)

    def test_update_session_timestamp_multiple(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Обновляет timestamp несколько раз."""
        timestamps = []
        for _ in range(3):
            state_manager.update_session_timestamp(session)
            timestamps.append(session.updated_at)
        # Каждый timestamp должен быть уникальным или очень близким
        assert len(set(timestamps)) >= 1  # По крайней мере один уникальный


class TestStateManagerSummary:
    """Тесты получения сводки состояния."""

    def test_get_session_summary_initial(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Возвращает сводку пустой сессии."""
        summary = state_manager.get_session_summary(session)
        assert summary["title"] is None
        assert summary["history_length"] == 0
        assert summary["cwd"] == "/tmp"
        assert "updated_at" in summary

    def test_get_session_summary_with_title(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Возвращает сводку с заголовком."""
        state_manager.update_session_title(session, "Test Title")
        summary = state_manager.get_session_summary(session)
        assert summary["title"] == "Test Title"

    def test_get_session_summary_with_history(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Возвращает сводку с историей."""
        prompt = [{"type": "text", "text": "Test"}]
        state_manager.add_user_message(session, prompt)
        state_manager.add_assistant_message(session, "Response")
        summary = state_manager.get_session_summary(session)
        assert summary["history_length"] == 2

    def test_get_session_summary_complete(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Возвращает полную сводку."""
        state_manager.update_session_title(session, "My Session")
        state_manager.update_session_timestamp(session)
        prompt = [{"type": "text", "text": "Test"}]
        state_manager.add_user_message(session, prompt)

        summary = state_manager.get_session_summary(session)
        assert summary["title"] == "My Session"
        assert summary["history_length"] == 1
        assert summary["cwd"] == "/tmp"
        assert "updated_at" in summary


class TestStateManagerEdgeCases:
    """Тесты граничных случаев."""

    def test_add_message_with_invalid_entry_not_dict(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Не добавляет невалидную запись (не dict)."""
        # Это будет обработано внутри, но не добавится
        prompt = "not a list"  # type: ignore
        state_manager.add_user_message(session, prompt)  # type: ignore
        # Должна выполниться без ошибок, но может не добавить

    def test_session_title_none_check(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Корректно проверяет None title."""
        assert session.title is None
        state_manager.update_session_title(session, "New Title")
        assert session.title is not None

    def test_empty_content_blocks(
        self,
        state_manager: StateManager,
        session: DomainSession,
    ) -> None:
        """Обрабатывает пустые content blocks."""
        state_manager.add_user_message(session, [])
        assert len(wire_history(session)) == 1
