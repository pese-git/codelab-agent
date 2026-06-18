"""PlanUpdateHandler - обработчик обновлений плана.

Обрабатывает тип обновления:
- plan: обновление плана выполнения агента
"""

from __future__ import annotations

from typing import Any

from codelab.client.presentation.chat.context import ChatUpdateContext


class PlanUpdateHandler:
    """Обработчик обновлений плана выполнения.

    Форматирует записи плана и обновляет PlanViewModel для отображения в UI.
    """

    def can_handle(self, update_type: str) -> bool:
        """Проверяет, может ли handler обработать этот тип update.

        Args:
            update_type: Тип обновления из update.sessionUpdate

        Returns:
            True если update_type это plan
        """
        return update_type == "plan"

    def handle(self, update_data: dict[str, Any], context: ChatUpdateContext) -> None:
        """Обрабатывает update плана.

        Args:
            update_data: Полные данные обновления от сервера
            context: Контекст с состоянием и сервисами
        """
        update = update_data.get("params", {}).get("update", {})
        entries = update.get("entries", [])

        context.logger.info(
            "plan_update_received",
            session_id=context.session_id,
            entries_count=len(entries),
            has_plan_vm=context.plan_vm is not None,
        )

        if not entries:
            # Пустой план - очищаем
            if context.plan_vm is not None:
                context.plan_vm.set_plan("")
            return

        if context.plan_vm is None:
            context.logger.debug(
                "plan_vm_not_available",
                session_id=context.session_id,
            )
            return

        # Форматируем план для отображения
        plan_text = self._format_plan(entries)
        context.plan_vm.set_plan(plan_text)

        context.logger.info(
            "plan_updated_in_view_model",
            session_id=context.session_id,
            entries_count=len(entries),
        )

    def _format_plan(self, entries: list[dict[str, Any]]) -> str:
        """Форматирует записи плана в читаемый текст.

        Args:
            entries: Список записей плана

        Returns:
            Отформатированный текст плана
        """
        lines = ["План:"]
        for entry in entries:
            content = entry.get("content", "")
            priority = entry.get("priority", "medium")
            status = entry.get("status", "pending")
            lines.append(f"- [{status}] ({priority}) {content}")
        return "\n".join(lines)
