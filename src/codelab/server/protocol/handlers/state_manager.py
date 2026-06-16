"""Менеджер состояния сессии и истории промптов.

Содержит логику управления SessionState, историей и метаданными сессии.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from ..state import SessionState

if TYPE_CHECKING:
    pass

# Используем structlog для структурированного логирования
logger = structlog.get_logger()


class StateManager:
    """Управляет состоянием сессии и историей промптов.

    Ответственность:
    - Управление состоянием SessionState
    - Обновление истории (история)
    - Управление заголовком сессии (title)
    - Синхронизация временных меток (updated_at)
    """

    def update_session_title(
        self,
        session: SessionState,
        text_preview: str,
    ) -> None:
        """Устанавливает title сессии из первого пользовательского запроса.

        Если заголовок уже установлен, не перезаписывает его.
        Обрезает preview до 80 символов.

        Args:
            session: Состояние сессии
            text_preview: Текст для заголовка (будет обрезан до 80 символов)
        """
        if session.title is None and text_preview:
            stripped = text_preview.strip()
            if stripped:
                session.title = stripped[:80]
                logger.debug(
                    "session title set",
                    session_id=session.session_id,
                    title=session.title,
                )

    def add_user_message(
        self,
        session: SessionState,
        prompt: list[dict[str, Any]],
    ) -> None:
        """Добавляет пользовательское сообщение в историю.

        Args:
            session: Состояние сессии
            prompt: Массив content blocks из request
        """
        # Добавляем полный prompt как запись истории
        history_entry = {
            "role": "user",
            "content": prompt,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        sanitized = _sanitize_history_entry(history_entry)
        if sanitized is not None:
            session.history.append(sanitized)
            logger.debug(
                "user message added to history",
                session_id=session.session_id,
                message_length=len(prompt),
            )

    def add_assistant_message(
        self,
        session: SessionState,
        content: str | dict[str, Any],
    ) -> None:
        """Добавляет ответ ассистента в историю.

        Args:
            session: Состояние сессии
            content: Текст или структурированный контент ответа
        """
        # Нормализуем content - может быть строка или dict
        if isinstance(content, str):
            history_entry = {
                "role": "assistant",
                "text": content,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        else:
            history_entry = {
                "role": "assistant",
                "content": content,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        sanitized = _sanitize_history_entry(history_entry)
        if sanitized is not None:
            session.history.append(sanitized)
            logger.debug(
                "assistant message added to history",
                session_id=session.session_id,
                content_type=type(content).__name__,
            )

    def update_session_timestamp(self, session: SessionState) -> None:
        """Обновляет updated_at на текущее время в UTC ISO 8601.

        Args:
            session: Состояние сессии
        """
        session.updated_at = datetime.now(UTC).isoformat()
        logger.debug(
            "session timestamp updated",
            session_id=session.session_id,
            timestamp=session.updated_at,
        )

    def add_event(
        self,
        session: SessionState,
        event_data: dict[str, Any],
    ) -> None:
        """Добавляет событие в историю событий сессии.

        Используется для сохранения системных уведомлений: session/update,
        permission requests, tool_call updates и т.д.

        Args:
            session: Состояние сессии
            event_data: Данные события (будет добавлена временная метка)
        """
        # Добавляем временную метку к событию если еще не добавлена
        event_entry = event_data.copy() if isinstance(event_data, dict) else event_data
        if isinstance(event_entry, dict) and "timestamp" not in event_entry:
            event_entry["timestamp"] = datetime.now(UTC).isoformat()

        session.events_history.append(event_entry)
        logger.debug(
            "event added to events_history",
            session_id=session.session_id,
            event_type=event_entry.get("type", "unknown"),
        )

    def get_session_summary(self, session: SessionState) -> dict[str, Any]:
        """Возвращает сводку состояния сессии для notifications.

        Returns:
            {"title": ..., "updated_at": ..., "history_length": ...}
        """
        return {
            "title": session.title,
            "updated_at": session.updated_at,
            "history_length": len(session.history),
            "cwd": session.cwd,
        }


def _sanitize_history_entry(
    entry: Any,
) -> Any | None:
    """Валидирует запись истории перед добавлением.

    Проверяет, что запись имеет базовую структуру (роль и контент).

    Args:
        entry: Запись из истории

    Returns:
        Нормализованная запись или None если невалидна
    """
    if not isinstance(entry, dict):
        logger.warning("history entry is not dict", entry_type=type(entry).__name__)
        return None

    # Требуем role
    if "role" not in entry:
        logger.warning("history entry missing role field")
        return None

    # Требуем хотя бы один из content/text/content/message
    has_content = any(key in entry for key in ["content", "text", "message"])
    if not has_content:
        logger.warning("history entry missing content fields")
        return None

    return entry


def _extract_text_from_content_blocks(blocks: list[dict[str, Any]]) -> str:
    """Извлекает текстовый preview из content blocks.

    Берет первый текстовый блок из массива content.

    Args:
        blocks: Массив content blocks

    Returns:
        Текстовый preview или пустая строка
    """
    if not isinstance(blocks, list):
        return ""

    for block in blocks:
        if (
            isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ):
            return block["text"]

    return ""
