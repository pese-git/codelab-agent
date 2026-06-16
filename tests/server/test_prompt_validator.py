"""
Тесты для PromptValidator.

Проверяет валидацию параметров session/prompt запроса и состояния сессии.
"""

import pytest

from codelab.server.exceptions import InvalidStateError, ValidationError
from codelab.server.protocol.prompt_handlers import PromptValidator
from codelab.server.protocol.state import ActiveTurnState, SessionState


class TestPromptValidatorValidateRequest:
    """Тесты для валидации параметров session/prompt запроса."""

    def test_validate_request_with_valid_string_content(self) -> None:
        """Тест валидации корректных параметров со строковым content."""
        params = {
            "sessionId": "sess_1",
            "content": "Hello, world!",
        }
        # Не должно выбросить исключение
        PromptValidator.validate_request(params)

    def test_validate_request_with_valid_list_content(self) -> None:
        """Тест валидации корректных параметров со списком content."""
        params = {
            "sessionId": "sess_2",
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": "World"},
            ],
        }
        # Не должно выбросить исключение
        PromptValidator.validate_request(params)

    def test_validate_request_missing_session_id(self) -> None:
        """Тест отсутствия обязательного параметра sessionId."""
        params = {
            "content": "Hello, world!",
        }
        with pytest.raises(ValidationError, match="Отсутствует обязательный параметр sessionId"):
            PromptValidator.validate_request(params)

    def test_validate_request_empty_session_id(self) -> None:
        """Тест пустого значения sessionId."""
        params = {
            "sessionId": "",
            "content": "Hello, world!",
        }
        with pytest.raises(ValidationError, match="sessionId должен быть непустой строкой"):
            PromptValidator.validate_request(params)

    def test_validate_request_invalid_session_id_type(self) -> None:
        """Тест некорректного типа sessionId."""
        params = {
            "sessionId": 123,
            "content": "Hello, world!",
        }
        with pytest.raises(ValidationError, match="sessionId должен быть непустой строкой"):
            PromptValidator.validate_request(params)

    def test_validate_request_missing_content(self) -> None:
        """Тест отсутствия обязательного параметра content."""
        params = {
            "sessionId": "sess_1",
        }
        with pytest.raises(ValidationError, match="Отсутствует обязательный параметр content"):
            PromptValidator.validate_request(params)

    def test_validate_request_empty_string_content(self) -> None:
        """Тест пустого строкового content."""
        params = {
            "sessionId": "sess_1",
            "content": "",
        }
        with pytest.raises(ValidationError, match="content не может быть пустой строкой"):
            PromptValidator.validate_request(params)

    def test_validate_request_whitespace_only_content(self) -> None:
        """Тест content содержащего только пробелы."""
        params = {
            "sessionId": "sess_1",
            "content": "   \t\n   ",
        }
        with pytest.raises(ValidationError, match="content не может быть пустой строкой"):
            PromptValidator.validate_request(params)

    def test_validate_request_empty_list_content(self) -> None:
        """Тест пустого списка content."""
        params = {
            "sessionId": "sess_1",
            "content": [],
        }
        with pytest.raises(ValidationError, match="content не может быть пустым списком"):
            PromptValidator.validate_request(params)

    def test_validate_request_invalid_content_type(self) -> None:
        """Тест некорректного типа content."""
        params = {
            "sessionId": "sess_1",
            "content": 123,
        }
        with pytest.raises(ValidationError, match="content должен быть строкой или списком"):
            PromptValidator.validate_request(params)

    def test_validate_request_content_dict_is_invalid(self) -> None:
        """Тест что словарь не является валидным content."""
        params = {
            "sessionId": "sess_1",
            "content": {"type": "text", "text": "Hello"},
        }
        with pytest.raises(ValidationError, match="content должен быть строкой или списком"):
            PromptValidator.validate_request(params)


class TestPromptValidatorValidateSessionState:
    """Тесты для валидации состояния сессии."""

    def test_validate_session_state_without_active_turn(self) -> None:
        """Тест валидации сессии без активного turn."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=None,
        )
        # Не должно выбросить исключение
        PromptValidator.validate_session_state(session)

    def test_validate_session_state_with_active_turn(self) -> None:
        """Тест обнаружения активного turn в сессии."""
        active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
        )
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=active_turn,
        )
        with pytest.raises(
            InvalidStateError,
            match="уже имеет активный turn",
        ):
            PromptValidator.validate_session_state(session)

    def test_validate_session_state_error_message_includes_session_id(
        self,
    ) -> None:
        """Тест что сообщение об ошибке содержит ID сессии."""
        session_id = "sess_test_123"
        active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id=session_id,
        )
        session = SessionState(
            session_id=session_id,
            cwd="/tmp",
            mcp_servers=[],
            active_turn=active_turn,
        )
        with pytest.raises(
            InvalidStateError,
            match=session_id,
        ):
            PromptValidator.validate_session_state(session)
