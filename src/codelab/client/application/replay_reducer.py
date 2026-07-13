"""Пересборка сообщений чата из replay-уведомлений `session/update`.

Прикладная трансформация протокол → сообщения: без Observable, без I/O.
Вынесена из presentation (ChatViewModel), чтобы единый алгоритм восстановления
использовался и при живом `session/load`, и при загрузке из persisted-кэша.
"""

from __future__ import annotations

from typing import Any


class ReplayReducer:
    """Собирает список сообщений чата из raw `session/update` replay-уведомлений.

    Последовательные message-chunks одной роли агрегируются в одно сообщение
    (streaming агента приходит порциями, но в истории должен быть цельным).
    """

    _ROLE_BY_UPDATE = {
        "user_message_chunk": "user",
        "agent_message_chunk": "assistant",
    }

    def reduce(
        self,
        session_id: str,
        replay_updates: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Пересобирает сообщения для одной сессии.

        Args:
            session_id: ID сессии — updates других сессий игнорируются.
            replay_updates: Список raw-уведомлений `session/update`.

        Returns:
            Список сообщений `{"role", "content"}` в порядке появления.
        """
        messages: list[dict[str, str]] = []
        last_role: str | None = None
        current_text_parts: list[str] = []

        for update_data in replay_updates:
            params = update_data.get("params", {})
            if params.get("sessionId") != session_id:
                continue

            update = params.get("update", {})
            role = self._ROLE_BY_UPDATE.get(update.get("sessionUpdate"))
            if role is None:
                continue

            content = update.get("content")
            if not isinstance(content, dict):
                continue

            text = content.get("text")
            if not isinstance(text, str) or text == "":
                continue

            # Смена роли завершает накопленное сообщение.
            if role != last_role and last_role is not None:
                messages.append({"role": last_role, "content": "".join(current_text_parts)})
                current_text_parts = []

            last_role = role
            current_text_parts.append(text)

        if last_role is not None and current_text_parts:
            messages.append({"role": last_role, "content": "".join(current_text_parts)})

        return messages
