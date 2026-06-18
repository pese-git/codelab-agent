"""Менеджер построения и валидации планов выполнения.

Содержит логику парсинга, валидации и построения план-related notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from ...messages import ACPMessage
from ..state import PromptDirectives, SessionState

if TYPE_CHECKING:
    pass

# Используем structlog для структурированного логирования
logger = structlog.get_logger()


class PlanBuilder:
    """Управляет построением и валидацией планов выполнения.

    Ответственность:
    - Парсинг plan entries из directives
    - Валидация структуры плана
    - Построение plan-related notifications
    - Нормализация plan entries
    """

    def should_publish_plan(self, directives: PromptDirectives) -> bool:
        """Нужно ли публиковать план в текущем turn.

        Returns:
            True если directives.publish_plan=True и есть план entries
        """
        if not directives.publish_plan:
            return False

        if directives.plan_entries is None:
            return False

        return bool(directives.plan_entries)

    def validate_plan_entries(
        self,
        raw_entries: Any,
    ) -> list[dict[str, str]] | None:
        """Валидирует и нормализует структуру plan entries.

        Args:
            raw_entries: Сырые entries из directives или LLM response

        Returns:
            Нормализованный список {content, priority, status} или None
        """
        if not isinstance(raw_entries, list) or not raw_entries:
            logger.debug("plan entries validation: not a non-empty list")
            return None

        normalized_entries: list[dict[str, str]] = []
        allowed_priorities = {"low", "medium", "high"}
        allowed_statuses = {"pending", "in_progress", "completed"}

        for entry in raw_entries:
            if not isinstance(entry, dict):
                logger.debug(
                    "plan entry validation: not a dict",
                    entry_type=type(entry).__name__,
                )
                continue

            # Требуем content (может быть title или content)
            content = entry.get("content") or entry.get("title")
            if not isinstance(content, str) or not content.strip():
                logger.debug("plan entry validation: missing or invalid content")
                continue

            # Нормализуем priority
            raw_priority = entry.get("priority")
            priority = raw_priority if isinstance(raw_priority, str) else "medium"
            if priority not in allowed_priorities:
                priority = "medium"

            # Нормализуем status
            raw_status = entry.get("status")
            status = raw_status if isinstance(raw_status, str) else "pending"
            if status not in allowed_statuses:
                status = "pending"

            normalized_entries.append(
                {
                    "content": content.strip(),
                    "priority": priority,
                    "status": status,
                }
            )

        return normalized_entries or None

    def normalize_plan_entries(
        self,
        raw_entries: Any,
    ) -> list[dict[str, str]] | None:
        """Alias для validate_plan_entries для обратной совместимости.

        Args:
            raw_entries: Сырые entries из directives или LLM response

        Returns:
            Нормализованный список {content, priority, status} или None
        """
        return self.validate_plan_entries(raw_entries)

    def build_plan_notification(
        self,
        session_id: str,
        plan_entries: list[dict[str, str]],
    ) -> ACPMessage:
        """Строит session/update notification с планом.

        Формат соответствует протоколу ACP (Agent Client Protocol):
        - sessionUpdate: "plan"
        - entries: список {content, priority, status}

        Args:
            session_id: ID сессии
            plan_entries: Нормализованные entries с content, priority, status

        Returns:
            ACPMessage с типом session/update и plan
        """
        # Используем entries напрямую — они уже в правильном формате ACP
        # {content, priority, status}
        notification = ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "plan",
                    "entries": plan_entries,
                },
            },
        )

        logger.debug(
            "plan notification built",
            session_id=session_id,
            plan_entries_count=len(plan_entries),
        )
        return notification

    def extract_plan_from_directives(
        self,
        directives: PromptDirectives,
    ) -> list[dict[str, str]] | None:
        """Извлекает и валидирует план из PromptDirectives.

        Returns:
            Нормализованный план или None
        """
        if directives.plan_entries is None:
            return None

        return self.validate_plan_entries(directives.plan_entries)

    def update_session_plan(
        self,
        session: SessionState,
        plan_entries: list[dict[str, str]],
    ) -> None:
        """Обновляет latest_plan в сессии.

        Args:
            session: Состояние сессии
            plan_entries: Нормализованные entries
        """
        # Преобразуем для сохранения в сессии
        session.latest_plan = [
            {
                "title": entry.get("content", ""),
                "description": entry.get("description", ""),
            }
            for entry in plan_entries
        ]

        logger.debug(
            "session plan updated",
            session_id=session.session_id,
            plan_entries_count=len(session.latest_plan),
        )

    def build_plan_updates(
        self,
        session: SessionState,
        session_id: str,
        directives: PromptDirectives,
    ) -> list[ACPMessage]:
        """Строит все plan-related notifications.

        Returns:
            Список notifications если нужно публиковать план, иначе []
        """
        if not self.should_publish_plan(directives):
            return []

        plan_entries = self.extract_plan_from_directives(directives)
        if plan_entries is None:
            logger.debug("plan updates: no valid plan entries")
            return []

        # Обновляем план в сессии
        self.update_session_plan(session, plan_entries)

        # Строим notification
        notification = self.build_plan_notification(session_id, plan_entries)
        return [notification]


def _validate_entry_structure(entry: Any) -> bool:
    """Проверяет валидность одного entry.

    Требует content/title и опциональные description, priority, status.

    Args:
        entry: Entry для проверки

    Returns:
        True если entry имеет требуемую структуру
    """
    if not isinstance(entry, dict):
        return False

    # Требуем хотя бы content или title
    has_title = "content" in entry or "title" in entry
    if not has_title:
        return False

    # Если есть content, он должен быть строкой
    if "content" in entry and not isinstance(entry["content"], str):
        return False

    # Если есть title, он должен быть строкой
    return not ("title" in entry and not isinstance(entry["title"], str))


def _normalize_entry_fields(entry: dict[str, Any]) -> dict[str, str]:
    """Нормализует поля entry.

    Обрезает длинные значения, нормализует типы.

    Args:
        entry: Entry для нормализации

    Returns:
        Нормализованный entry
    """
    # Максимальные длины
    MAX_CONTENT_LENGTH = 200
    MAX_DESCRIPTION_LENGTH = 500

    content = entry.get("content") or entry.get("title", "")
    if isinstance(content, str):
        content = content.strip()[:MAX_CONTENT_LENGTH]

    description = entry.get("description", "")
    if isinstance(description, str):
        description = description.strip()[:MAX_DESCRIPTION_LENGTH]

    priority = entry.get("priority", "medium")
    if priority not in {"low", "medium", "high"}:
        priority = "medium"

    status = entry.get("status", "pending")
    if status not in {"pending", "in_progress", "completed", "cancelled"}:
        status = "pending"

    return {
        "content": content,
        "description": description,
        "priority": priority,
        "status": status,
    }


def _get_allowed_plan_keys() -> set[str]:
    """Спецификация разрешенных ключей в entry.

    Returns:
        Множество разрешенных ключей
    """
    return {
        "content",
        "title",
        "description",
        "priority",
        "status",
    }
