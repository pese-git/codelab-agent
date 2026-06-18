"""MessageChunkHandler - обработчик обновлений сообщений.

Обрабатывает типы обновлений:
- agent_message_chunk: фрагменты ответа агента
- user_message_chunk: фрагменты сообщений пользователя
"""

from __future__ import annotations

from typing import Any

from codelab.client.presentation.chat.context import ChatUpdateContext


class MessageChunkHandler:
    """Обработчик обновлений сообщений (agent/user message chunks).

    Добавляет текст в streaming_text для agent_message_chunk
    или в messages для user_message_chunk.
    """

    def can_handle(self, update_type: str) -> bool:
        """Проверяет, может ли handler обработать этот тип update.

        Args:
            update_type: Тип обновления из update.sessionUpdate

        Returns:
            True если update_type это agent_message_chunk или user_message_chunk
        """
        return update_type in {"agent_message_chunk", "user_message_chunk"}

    def handle(self, update_data: dict[str, Any], context: ChatUpdateContext) -> None:
        """Обрабатывает update сообщения.

        Args:
            update_data: Полные данные обновления от сервера
            context: Контекст с состоянием и сервисами
        """
        update = update_data.get("params", {}).get("update", {})
        content = update.get("content", {})
        text = content.get("text", "")

        if not text:
            context.logger.debug(
                "message_chunk_empty_text",
                update_type=update.get("sessionUpdate"),
            )
            return

        update_type = update.get("sessionUpdate")

        if update_type == "agent_message_chunk":
            self._handle_agent_chunk(text, context)
        elif update_type == "user_message_chunk":
            self._handle_user_chunk(text, context)

    def _handle_agent_chunk(self, text: str, context: ChatUpdateContext) -> None:
        """Обрабатывает фрагмент ответа агента.

        Добавляет текст в streaming_text и синхронизирует с UI.

        Args:
            text: Текст фрагмента
            context: Контекст с состоянием
        """
        context.state.append_streaming_text(text)
        if context.sink is not None:
            context.sink.sync_streaming(
                context.session_id,
                context.state.streaming_text,
                context.state.is_streaming,
            )

        context.logger.debug(
            "agent_message_chunk_processed",
            session_id=context.session_id,
            text_length=len(text),
            total_streaming_length=len(context.state.streaming_text),
        )

    def _handle_user_chunk(self, text: str, context: ChatUpdateContext) -> None:
        """Обрабатывает фрагмент сообщения пользователя.

        Добавляет сообщение в messages и синхронизирует с UI.

        Args:
            text: Текст фрагмента
            context: Контекст с состоянием
        """
        context.state.add_message("user", text)
        if context.sink is not None:
            context.sink.sync_messages(context.session_id, context.state.messages)

        context.logger.debug(
            "user_message_chunk_processed",
            session_id=context.session_id,
            text_length=len(text),
            total_messages=len(context.state.messages),
        )
