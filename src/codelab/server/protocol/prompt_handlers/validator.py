"""
Валидатор параметров session/prompt запроса.

Отвечает за валидацию входных параметров prompt запроса:
- Проверка обязательных полей (sessionId, content)
- Валидация типов и форматов
- Проверка состояния сессии
"""

from typing import Any

from codelab.server.exceptions import InvalidStateError, ValidationError
from codelab.server.protocol.state import SessionState


class PromptValidator:
    """Валидатор параметров session/prompt запроса."""

    @staticmethod
    def validate_request(params: dict[str, Any]) -> None:
        """
        Валидирует параметры session/prompt запроса.

        Args:
            params: Параметры запроса

        Raises:
            ValidationError: Если параметры некорректны
        """
        # Проверка sessionId
        if "sessionId" not in params:
            raise ValidationError("Отсутствует обязательный параметр sessionId")

        session_id = params["sessionId"]
        if not isinstance(session_id, str) or not session_id:
            raise ValidationError(f"sessionId должен быть непустой строкой, получен: {session_id}")

        # Проверка content
        if "content" not in params:
            raise ValidationError("Отсутствует обязательный параметр content")

        content = params["content"]
        if not isinstance(content, (str, list)):
            raise ValidationError(
                f"content должен быть строкой или списком, получен: {type(content)}"
            )

        if isinstance(content, str) and not content.strip():
            raise ValidationError("content не может быть пустой строкой")

        if isinstance(content, list) and len(content) == 0:
            raise ValidationError("content не может быть пустым списком")

    @staticmethod
    def validate_session_state(session: SessionState) -> None:
        """
        Валидирует состояние сессии перед обработкой prompt.

        Args:
            session: Состояние сессии

        Raises:
            InvalidStateError: Если сессия в некорректном состоянии
        """
        # Проверка, что нет активного turn
        if session.active_turn is not None:
            raise InvalidStateError(
                f"Сессия {session.session_id} уже имеет активный turn. "
                "Используйте session/cancel для отмены текущего turn."
            )
