"""ThreePhaseCompactor — 3-фазное сжатие контекста.

Слой C — Хранение (Phase 3).

Фазы: Prune → Skeletonize → Summarize.
Останавливается на первой достаточной фазе.
При недоступности LLM деградирует до Prune + Skeletonize.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

import structlog

from codelab.server.agent.context.budget import DefaultTokenBudgetManager
from codelab.server.agent.context.interfaces import (
    CodeSkeletonizer,
    ContextCompactor,
    ConversationSummarizer,
    TokenCounter,
)
from codelab.server.agent.core.message_sanitizer import MessageSanitizer
from codelab.server.llm.models import LLMMessage

if TYPE_CHECKING:
    from codelab.server.agent.context.models import ContextConfig
    from codelab.server.observability.metrics_tracker import MetricsTracker
    from codelab.server.observability.tracer import SpanContext, Tracer

logger = structlog.get_logger(__name__)

_MIN_HISTORY_LENGTH = 5
_KEEP_START = 2
_KEEP_END = 3

_FILE_BLOCK_PATTERN = re.compile(
    r'(<file\s+path=")([^"]+)(">)(.*?)(</file>)',
    re.DOTALL,
)


class ThreePhaseCompactor(ContextCompactor):
    """3-фазное сжатие: Prune → Skeletonize → Summarize.

    Останавливается на первой фазе, достаточной для помещения в бюджет.
    При недоступности LLM деградирует до Prune + Skeletonize.
    """

    def __init__(
        self,
        token_counter: TokenCounter,
        skeletonizer: CodeSkeletonizer | None = None,
        summarizer: ConversationSummarizer | None = None,
        sanitizer: MessageSanitizer | None = None,
        config: ContextConfig | None = None,
        metrics_tracker: MetricsTracker | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._token_counter = token_counter
        self._skeletonizer = skeletonizer
        self._summarizer = summarizer
        self._sanitizer = sanitizer or MessageSanitizer()
        self._budget_manager = DefaultTokenBudgetManager(config)
        self._metrics_tracker = metrics_tracker
        self._tracer = tracer

    async def compact_if_needed(
        self,
        messages: list[LLMMessage],
        *,
        max_context_tokens: int,
        reserved_tokens: int,
    ) -> list[LLMMessage]:
        """Сжать историю если превышает лимит.

        Последовательность: Prune → Skeletonize → Summarize.
        Останавливается на первой достаточной фазе.
        """
        start_time = time.time()
        trigger = max_context_tokens - reserved_tokens
        tokens_before = self._token_counter.count_messages(messages)

        span: SpanContext | None = None
        if self._tracer is not None:
            span = self._tracer.start_span(name="context.compact")

        logger.info(
            "context.compact.start",
            tokens_before=tokens_before,
            trigger=trigger,
            max_context_tokens=max_context_tokens,
            reserved_tokens=reserved_tokens,
            message_count=len(messages),
        )

        if tokens_before <= trigger:
            logger.debug("context.compact.not_needed", tokens=tokens_before, trigger=trigger)
            result = self._remove_orphaned_tool_results(messages)
            result = self._sanitizer.sanitize(result)
            if span is not None and self._tracer is not None:
                self._tracer.end_span(
                    span,
                    attributes={
                        "phase": "none",
                        "ratio": 1.0,
                        "tokens_before": tokens_before,
                        "tokens_after": self._token_counter.count_messages(result),
                        "degraded": False,
                    },
                )
            return result
        degraded = False
        degrade_reason = ""
        final_phase = "none"

        result = list(messages)

        result = self._phase_prune(result)
        tokens_after_prune = self._token_counter.count_messages(result)
        final_phase = "prune"
        logger.info(
            "context.compact.phase_prune",
            tokens_before=tokens_before,
            tokens_after=tokens_after_prune,
            trigger=trigger,
        )

        if tokens_after_prune <= trigger:
            return self._finalize(
                result,
                span,
                "prune",
                tokens_before,
                tokens_after_prune,
                degraded,
                degrade_reason,
                start_time,
            )

        if self._skeletonizer is not None:
            result = self._phase_skeletonize(result)
            tokens_after_skel = self._token_counter.count_messages(result)
            final_phase = "skeletonize"
            logger.info(
                "context.compact.phase_skeletonize",
                tokens_before=tokens_after_prune,
                tokens_after=tokens_after_skel,
                trigger=trigger,
            )

            if tokens_after_skel <= trigger:
                return self._finalize(
                    result,
                    span,
                    "skeletonize",
                    tokens_before,
                    tokens_after_skel,
                    degraded,
                    degrade_reason,
                    start_time,
                )

        if self._summarizer is not None:
            try:
                target_tokens = max(trigger // 4, 500)
                summary = await self._summarizer.summarize(
                    result,
                    target_tokens=target_tokens,
                )
                result = self._replace_middle_with_summary(result, summary)
                tokens_after_sum = self._token_counter.count_messages(result)
                final_phase = "summarize"
                logger.info(
                    "context.compact.phase_summarize",
                    tokens_before=tokens_after_skel if self._skeletonizer else tokens_after_prune,
                    tokens_after=tokens_after_sum,
                    trigger=trigger,
                )

                if tokens_after_sum <= trigger:
                    return self._finalize(
                        result,
                        span,
                        "summarize",
                        tokens_before,
                        tokens_after_sum,
                        degraded,
                        degrade_reason,
                        start_time,
                    )
            except Exception:
                logger.exception("context.compact.summarize_failed_degrading")
                degraded = True
                degrade_reason = "summarize_exception"
        else:
            degraded = True
            degrade_reason = "no_summarizer"
            logger.warning(
                "summarization_failed_degrade_to_prune",
                reason=degrade_reason,
            )

        result = self._phase_hard_truncate(result, trigger)
        final_phase = "hard_truncate"
        tokens_after_truncate = self._token_counter.count_messages(result)
        logger.warning(
            "context.compact.hard_truncate",
            tokens_before=tokens_before,
            tokens_after=tokens_after_truncate,
            trigger=trigger,
        )

        return self._finalize(
            result,
            span,
            final_phase,
            tokens_before,
            tokens_after_truncate,
            degraded,
            degrade_reason,
            start_time,
        )

    @staticmethod
    def _message_priority(msg: LLMMessage) -> int:
        """Определить приоритет сообщения для eviction.

        Приоритеты (из спецификации):
        - system = 10 (system_rules) — не вытесняется
        - user = 8 (user_prompt) — вытесняется при критическом переполнении
        - assistant = 6
        - tool = 4 (tool outputs) — вытесняется первым
        """
        if msg.role == "system":
            return 10
        if msg.role == "user":
            return 8
        if msg.role == "assistant":
            return 6
        if msg.role == "tool":
            return 4
        return 5

    def _phase_prune(self, messages: list[LLMMessage]) -> list[LLMMessage]:
        """Фаза 1: Priority-based удаление старых tool outputs.

        Сохраняет первые 2 и последние N сообщений.
        В middle удаляет сообщения с наименьшим приоритетом первыми.
        """
        if len(messages) <= _MIN_HISTORY_LENGTH:
            return list(messages)

        start = messages[:_KEEP_START]
        end = messages[-_KEEP_END:]
        middle = messages[_KEEP_START:-_KEEP_END]

        # Удаляем tool messages (priority=4) первыми
        pruned_middle = [msg for msg in middle if msg.role != "tool"]

        result = start + pruned_middle + end
        result = self._sanitize_assistant_tool_calls(result)
        return result

    def _phase_skeletonize(self, messages: list[LLMMessage]) -> list[LLMMessage]:
        """Фаза 2: AST-сжатие файлов кода в system messages."""
        if self._skeletonizer is None:
            return messages

        result: list[LLMMessage] = []
        for msg in messages:
            if msg.role == "system" and isinstance(msg.content, str):
                new_content = self._skeletonize_file_blocks(msg.content)
                result.append(
                    LLMMessage(
                        role=msg.role,
                        content=new_content,
                        tool_calls=msg.tool_calls,
                        tool_call_id=msg.tool_call_id,
                        name=msg.name,
                    )
                )
            else:
                result.append(msg)
        return result

    def _skeletonize_file_blocks(self, content: str) -> str:
        """Найти XML-блоки файлов и скелетировать их."""

        def replace_file_block(match: re.Match[str]) -> str:
            prefix = match.group(1)
            path = match.group(2)
            open_tag = match.group(3)
            code = match.group(4)
            close_tag = match.group(5)

            if not self._skeletonizer or not self._skeletonizer.can_handle(path):
                return match.group(0)

            try:
                from codelab.server.agent.context.skeletonizer.composite import (
                    CompositeSkeletonizer,
                )

                if isinstance(self._skeletonizer, CompositeSkeletonizer):
                    skeleton = self._skeletonizer.skeletonize_file(code, path)
                else:
                    skeleton = self._skeletonizer.skeletonize(code)
            except Exception:
                logger.exception("context.compact.skeletonize_failed", path=path)
                return match.group(0)

            original_tokens = self._token_counter.count(code)
            skeleton_tokens = self._token_counter.count(skeleton)

            if skeleton_tokens >= original_tokens:
                logger.info(
                    "skeleton_not_beneficial",
                    path=path,
                    original_tokens=original_tokens,
                    skeleton_tokens=skeleton_tokens,
                )
                return match.group(0)

            logger.debug(
                "context.compact.file_skeletonized",
                path=path,
                original_tokens=original_tokens,
                skeleton_tokens=skeleton_tokens,
                savings_ratio=1.0 - (skeleton_tokens / max(original_tokens, 1)),
            )

            return f"{prefix}{path}{open_tag}{skeleton}{close_tag}"

        return _FILE_BLOCK_PATTERN.sub(replace_file_block, content)

    def _pack_within_budget(
        self,
        messages: list[LLMMessage],
        budget: int,
        *,
        keep_metadata: bool,
    ) -> list[LLMMessage]:
        """Жадно набрать сообщения в пределах budget; переполняющее — усечь по остатку.

        Общий примитив для веток hard-truncate. `count_messages` аддитивен, поэтому
        накопленный `used` эквивалентен пересчёту токенов результата.

        Args:
            messages: Кандидаты (в желаемом порядке набора).
            budget: Лимит токенов.
            keep_metadata: Сохранять ли tool_calls/tool_call_id/name у усечённого
                сообщения (для evictable/истории — да; для protected system — нет).
        """
        result: list[LLMMessage] = []
        used = 0
        for msg in messages:
            msg_tokens = self._token_counter.count_messages([msg])
            if used + msg_tokens <= budget:
                result.append(msg)
                used += msg_tokens
                continue

            content = msg.content if isinstance(msg.content, str) else str(msg.content or "")
            remaining = budget - used
            if remaining > 0 and content:
                bounded = self._budget_manager.bound_content(content, remaining)
                if keep_metadata:
                    result.append(
                        LLMMessage(
                            role=msg.role,
                            content=bounded,
                            tool_calls=msg.tool_calls,
                            tool_call_id=msg.tool_call_id,
                            name=msg.name,
                        )
                    )
                else:
                    result.append(LLMMessage(role=msg.role, content=bounded))
            break
        return result

    def _phase_hard_truncate(
        self,
        messages: list[LLMMessage],
        trigger: int,
    ) -> list[LLMMessage]:
        """Жёсткое усечение как последний resort.

        Учитывает приоритеты сообщений:
        - priority >= 10 (system) — не вытесняются при обычном переполнении
        - priority >= 8 (user) — вытесняются при критическом переполнении
        - priority < 8 — вытесняются первыми (по возрастанию приоритета)
        """
        if len(messages) <= _MIN_HISTORY_LENGTH:
            start_tokens = self._token_counter.count_messages(messages)
            if start_tokens <= trigger:
                return messages
            return self._pack_within_budget(messages, trigger, keep_metadata=True)

        start = messages[:_KEEP_START]
        end = messages[-_KEEP_END:]
        middle = messages[_KEEP_START:-_KEEP_END]

        start_tokens = self._token_counter.count_messages(start)
        end_tokens = self._token_counter.count_messages(end)
        fixed_tokens = start_tokens + end_tokens

        if fixed_tokens >= trigger:
            logger.error(
                "critical_items_exceed_budget",
                start_tokens=start_tokens,
                end_tokens=end_tokens,
                trigger=trigger,
            )
            return start + end

        middle_budget = trigger - fixed_tokens
        result_middle = self._evict_middle_by_priority(middle, middle_budget, trigger)
        return start + result_middle + end

    def _evict_middle_by_priority(
        self,
        middle: list[LLMMessage],
        middle_budget: int,
        trigger: int,
    ) -> list[LLMMessage]:
        """Вытеснить средние сообщения по приоритету в пределах middle_budget.

        Защищённые (priority >= 10) сохраняются; evictable вытесняются по
        возрастанию приоритета. При критическом переполнении (даже защищённые не
        помещаются) усекаются сами защищённые. Порядок оставшихся — исходный.
        """
        protected = [msg for msg in middle if self._message_priority(msg) >= 10]
        evictable = [msg for msg in middle if self._message_priority(msg) < 10]

        # Сортируем evictable по приоритету (ascending) — вытесняем наименьшие первыми
        evictable.sort(key=lambda msg: self._message_priority(msg))

        protected_tokens = self._token_counter.count_messages(protected)
        evictable_budget = middle_budget - protected_tokens

        if evictable_budget <= 0:
            # Критическое переполнение — даже защищённые не помещаются
            logger.error(
                "critical_items_exceed_budget",
                protected_tokens=protected_tokens,
                middle_budget=middle_budget,
                trigger=trigger,
            )
            # Усекаем защищённые как последнюю меру
            return self._pack_within_budget(protected, middle_budget, keep_metadata=False)

        # Усекаем evictable по приоритету
        bounded_evictable = self._pack_within_budget(
            evictable, evictable_budget, keep_metadata=True
        )

        # Восстанавливаем порядок: protected + evictable в исходном порядке
        kept_evictable_ids = {id(msg) for msg in bounded_evictable}
        return protected + [
            msg
            for msg in middle
            if id(msg) in kept_evictable_ids and self._message_priority(msg) < 10
        ]

    def _replace_middle_with_summary(
        self,
        messages: list[LLMMessage],
        summary: LLMMessage,
    ) -> list[LLMMessage]:
        """Заменить средние сообщения суммаризацией."""
        if len(messages) <= _MIN_HISTORY_LENGTH:
            return messages

        start = messages[:_KEEP_START]
        end = messages[-_KEEP_END:]
        return start + [summary] + end

    def _finalize(
        self,
        result: list[LLMMessage],
        span: SpanContext | None,
        phase: str,
        tokens_before: int,
        tokens_after: int,
        degraded: bool,
        degrade_reason: str,
        start_time: float,
    ) -> list[LLMMessage]:
        """Финализация: санитизация + метрики + трейсинг."""
        result = self._remove_orphaned_tool_results(result)
        result = self._sanitizer.sanitize(result)

        tokens_final = self._token_counter.count_messages(result)
        ratio = tokens_final / max(tokens_before, 1)
        elapsed_ms = (time.time() - start_time) * 1000

        logger.info(
            "context.compact.complete",
            phase=phase,
            tokens_before=tokens_before,
            tokens_after=tokens_final,
            ratio=ratio,
            degraded=degraded,
            degrade_reason=degrade_reason,
            elapsed_ms=elapsed_ms,
        )

        if span is not None and self._tracer is not None:
            self._tracer.end_span(
                span,
                attributes={
                    "phase": phase,
                    "ratio": ratio,
                    "tokens_before": tokens_before,
                    "tokens_after": tokens_final,
                    "degraded": degraded,
                    "degrade_reason": degrade_reason,
                },
            )

        if self._metrics_tracker is not None:
            self._metrics_tracker.record_context_compaction(
                ratio=ratio,
                phase=phase,
                degraded=degraded,
                reason=degrade_reason,
                session_id="",
            )

        return result

    @staticmethod
    def _collect_tool_call_ids(messages: list[LLMMessage]) -> set[str]:
        """Собрать все tool_call IDs из сообщений."""
        ids: set[str] = set()
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    ids.add(tc.id)
        return ids

    @staticmethod
    def _collect_tool_result_ids(messages: list[LLMMessage]) -> set[str]:
        """Собрать все tool_result IDs из сообщений."""
        ids: set[str] = set()
        for msg in messages:
            if msg.role == "tool" and msg.tool_call_id:
                ids.add(msg.tool_call_id)
        return ids

    @staticmethod
    def _remove_orphaned_tool_results(messages: list[LLMMessage]) -> list[LLMMessage]:
        """Удалить tool_result без соответствующего tool_call."""
        tool_call_ids = ThreePhaseCompactor._collect_tool_call_ids(messages)
        result: list[LLMMessage] = []
        for msg in messages:
            if msg.role == "tool" and msg.tool_call_id and msg.tool_call_id not in tool_call_ids:
                logger.debug(
                    "orphaned_tool_result_dropped",
                    tool_call_id=msg.tool_call_id,
                )
                continue
            result.append(msg)
        return result

    @staticmethod
    def _sanitize_assistant_tool_calls(messages: list[LLMMessage]) -> list[LLMMessage]:
        """Удалить tool_calls из assistant, если нет соответствующих tool results."""
        tool_result_ids = ThreePhaseCompactor._collect_tool_result_ids(messages)
        result: list[LLMMessage] = []
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                remaining = [tc for tc in msg.tool_calls if tc.id in tool_result_ids]
                if not remaining:
                    if msg.content:
                        result.append(
                            LLMMessage(
                                role="assistant",
                                content=msg.content,
                            )
                        )
                    continue
                if len(remaining) != len(msg.tool_calls):
                    result.append(
                        LLMMessage(
                            role="assistant",
                            content=msg.content,
                            tool_calls=remaining,
                        )
                    )
                else:
                    result.append(msg)
            else:
                result.append(msg)
        return result
