"""ChildSessionManager — менеджер дочерних сессий для мультиагента.

Слой D — Мультиагентный обмен (Phase 6).

Реализует изоляцию субагентов в child-сессиях:
- create_child() создаёт изолированную сессию с parent_session_id
- collect_summary() суммаризирует результат child-сессии для родителя
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from codelab.server.agent.context.interfaces import ChildSessionManager
from codelab.server.agent.context.models import SubagentResult

if TYPE_CHECKING:
    from codelab.server.agent.context.interfaces import ConversationSummarizer, TokenCounter
    from codelab.server.protocol.session_factory import SessionFactory
    from codelab.server.storage.base import SessionStorage

logger = structlog.get_logger(__name__)


class DefaultChildSessionManager(ChildSessionManager):
    """Менеджер дочерних сессий с изоляцией (дефолт MVP).

    Создаёт child-сессии через SessionFactory, суммаризирует результаты
    через ConversationSummarizer. Федеративный шаринг не используется
    (кандидат на отказ согласно ADR-002).
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        session_storage: SessionStorage,
        summarizer: ConversationSummarizer,
        token_counter: TokenCounter,
    ) -> None:
        self._session_factory = session_factory
        self._session_storage = session_storage
        self._summarizer = summarizer
        self._token_counter = token_counter

    async def create_child(
        self,
        parent: object,
        subagent_scope: str,
    ) -> object:
        """Создать изолированную дочернюю сессию.

        Args:
            parent: Родительская сессия (SessionState)
            subagent_scope: Идентификатор скоупа субагента

        Returns:
            Новая child-сессия (SessionState) с parent_session_id
        """
        parent_state = parent
        parent_session_id = getattr(parent_state, "session_id", None)
        parent_cwd = getattr(parent_state, "cwd", "/tmp")

        # Генерируем уникальный session_id для child
        child_session_id = f"{parent_session_id}_child_{subagent_scope}"

        logger.info(
            "context.multiagent.create_child",
            parent_session_id=parent_session_id,
            child_session_id=child_session_id,
            subagent_scope=subagent_scope,
        )

        # Создаём child-сессию через SessionFactory
        child_state = self._session_factory.create_session(
            cwd=parent_cwd,
            session_id=child_session_id,
        )

        # Устанавливаем parent_session_id (миграция schema_version=7)
        # SessionState не имеет этого поля в текущей версии, но оно зарезервировано
        # для будущей миграции. Пока используем config_values.
        child_state.config_values["parent_session_id"] = parent_session_id or ""
        child_state.config_values["subagent_scope"] = subagent_scope

        # Сохраняем child-сессию в storage
        await self._session_storage.save_session(child_state)

        logger.info(
            "context.multiagent.child_created",
            child_session_id=child_session_id,
            parent_session_id=parent_session_id,
        )

        return child_state

    async def collect_summary(self, child: object) -> SubagentResult:
        """Собрать результат дочерней сессии.

        Суммаризирует историю child-сессии через ConversationSummarizer.
        Возвращает SubagentResult с summary для родителя.

        Args:
            child: Дочерняя сессия (SessionState)

        Returns:
            SubagentResult с суммаризованным результатом
        """
        child_state = child
        child_session_id = getattr(child_state, "session_id", "unknown")
        subagent_scope = child_state.config_values.get("subagent_scope", "unknown")

        logger.info(
            "context.multiagent.collect_summary.start",
            child_session_id=child_session_id,
            subagent_scope=subagent_scope,
        )

        # Получаем историю child-сессии
        history = getattr(child_state, "history", [])
        if not history:
            logger.warning(
                "context.multiagent.collect_summary.empty_history",
                child_session_id=child_session_id,
            )
            return SubagentResult(
                summary="(субагент не выполнил действий)",
                token_count=0,
                source_scope=subagent_scope,
            )

        # Конвертируем историю в LLMMessage для суммаризации
        from codelab.server.agent.core.history_builder import HistoryBuilder

        history_builder = HistoryBuilder()
        messages = history_builder.build(history)

        # Суммаризируем через ConversationSummarizer
        target_tokens = min(len(messages) * 100, 2000)  # Ограничение по токенам
        summary_message = await self._summarizer.summarize(messages, target_tokens=target_tokens)

        # Извлекаем текст из LLMMessage
        if hasattr(summary_message, "content"):
            content = summary_message.content
            if isinstance(content, str):
                summary_text = content
            elif isinstance(content, list):
                # ContentPart list — конкатенируем текстовые части
                summary_text = " ".join(
                    part.text if hasattr(part, "text") else str(part) for part in content
                )
            else:
                summary_text = str(content)
        else:
            summary_text = str(summary_message)

        # Подсчитываем токены summary
        summary_tokens = self._token_counter.count_messages([summary_message])

        logger.info(
            "context.multiagent.collect_summary.complete",
            child_session_id=child_session_id,
            subagent_scope=subagent_scope,
            summary_length=len(summary_text),
            summary_tokens=summary_tokens,
            history_messages=len(messages),
        )

        return SubagentResult(
            summary=summary_text,
            token_count=summary_tokens,
            source_scope=subagent_scope,
        )
