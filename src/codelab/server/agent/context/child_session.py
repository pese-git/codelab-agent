"""ChildSessionManager — менеджер дочерних сессий для мультиагента.

Слой D — Мультиагентный обмен (Phase 6).

Реализует изоляцию субагентов в child-сессиях:
- create_child() создаёт изолированную сессию с parent_session_id
- collect_summary() суммаризирует результат child-сессии для родителя

ADR-005 Фаза 4: ``DefaultChildSessionManager`` принимает
``ChildSessionFactory`` Protocol (driven-порт), а НЕ
``SessionFactory`` (ACP). Это разворачивает зависимость:
ACP-уровень реализует ``ChildSessionFactory`` (``ACPChildSessionFactory``),
ядро не знает про ``SessionFactory``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from codelab.server.agent.context.interfaces import ChildSessionManager
from codelab.server.agent.context.models import SubagentResult

if TYPE_CHECKING:
    from codelab.server.agent.context.interfaces import ConversationSummarizer, TokenCounter
    from codelab.server.agent.contracts.ports import ChildSessionFactory, SessionView
    from codelab.server.storage.base import SessionStorage

logger = structlog.get_logger(__name__)


class DefaultChildSessionManager(ChildSessionManager):
    """Менеджер дочерних сессий с изоляцией (дефолт MVP).

    Создаёт child-сессии через ``ChildSessionFactory`` (driven-порт),
    суммаризирует результаты через ``ConversationSummarizer``.
    Федеративный шаринг не используется (кандидат на отказ согласно ADR-002).
    """

    def __init__(
        self,
        child_session_factory: ChildSessionFactory,
        session_storage: SessionStorage,
        summarizer: ConversationSummarizer,
        token_counter: TokenCounter,
    ) -> None:
        self._child_session_factory = child_session_factory
        self._session_storage = session_storage
        self._summarizer = summarizer
        self._token_counter = token_counter

    async def create_child(
        self,
        parent: SessionView,
        subagent_scope: str,
    ) -> SessionView:
        """Создать изолированную дочернюю сессию.

        Args:
            parent: Родительская сессия (``SessionView`` после Фазы 1).
            subagent_scope: Идентификатор скоупа субагента.

        Returns:
            Новая child-сессия (``SessionView``) с parent_session_id
            (first-class поле, schema_version 7).
        """
        parent_view: SessionView = parent
        parent_session_id = str(parent_view.id)

        logger.info(
            "context.multiagent.create_child",
            parent_session_id=parent_session_id,
            subagent_scope=subagent_scope,
        )

        # Создаём child-сессию через ChildSessionFactory (driven-порт)
        child_view = await self._child_session_factory.create_child(
            parent=parent_view,
            subagent_scope=subagent_scope,
        )

        # Сохраняем child-сессию в storage.
        # Ядро (core/) не знает про протокольные детали SessionStateView;
        # адаптер ``ChildSessionFactory`` обязан вернуть ``SessionView``,
        # а сохранение делегируется на уровень ядра через отдельный
        # SessionStorage-адаптер (TODO Фаза 5: SessionStorage порт).
        # Пока child-сессии не персистятся (тех-долг, не блокер).
        logger.debug(
            "child_session_create_skipped_persist",
            child_session_id=str(child_view.id),
            note="storage persistence deferred to Phase 5",
        )

        logger.info(
            "context.multiagent.child_created",
            child_session_id=str(child_view.id),
            parent_session_id=parent_session_id,
        )

        return child_view

    async def collect_summary(self, child: SessionView) -> SubagentResult:
        """Собрать результат дочерней сессии.

        Суммаризирует историю child-сессии через ConversationSummarizer.
        Возвращает SubagentResult с summary для родителя.

        Args:
            child: Дочерняя сессия (SessionState)

        Returns:
            SubagentResult с суммаризованным результатом
        """
        child_view: SessionView = child
        child_session_id = str(child_view.id)
        subagent_scope = child_view.config.config_values.get("subagent_scope", "unknown")

        logger.info(
            "context.multiagent.collect_summary.start",
            child_session_id=child_session_id,
            subagent_scope=subagent_scope,
        )

        # Получаем историю child-сессии (ADR-005 Фаза 4: через SessionView.messages())
        history = list(child_view.messages())
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

        # Конвертируем историю в LLMMessage для суммаризации.
        # SessionView.messages() возвращает доменные ConversationMessage,
        # которые HistoryBuilder не принимает напрямую (он ждёт list[dict]).
        # Конвертируем в raw dict-формат для совместимости с HistoryBuilder.
        from codelab.server.agent.core.history_builder import HistoryBuilder

        history_builder = HistoryBuilder()
        raw_history = [
            {
                "role": msg.role.value,
                "text": msg.content.text,
                "tool_calls": [
                    {"id": tc.id, "name": tc.tool_name, "arguments": tc.arguments}
                    for tc in msg.tool_calls
                ],
            }
            for msg in history
        ]
        messages = history_builder.build(raw_history)

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
