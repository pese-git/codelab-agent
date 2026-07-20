"""EnvelopeAssembler — сборка baseline/tail для двух режимов ContextManager.

Выделено из manager.py. Отвечает за формирование (baseline, fingerprint, tail,
reconcile_info) в режимах гидрации и инкрементальном (эпохи), включая tail из
истории сессии и замер длительности стадий tail/fingerprint.

Тайминги возвращаются в AssembledEnvelope, а не мутируют поля менеджера.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.agent.context.epoch import EpochManager
from codelab.server.llm.models import LLMMessage

if TYPE_CHECKING:
    from codelab.server.agent.context.manager import _SessionContext
    from codelab.server.agent.context.registry import ContextRegistryImpl
    from codelab.server.agent.history_builder import HistoryBuilder

logger = structlog.get_logger(__name__)


@dataclass
class AssembledEnvelope:
    """Результат сборки baseline/tail одного хода."""

    baseline: list[LLMMessage]
    baseline_fingerprint: str
    tail: list[LLMMessage]
    reconcile_info: dict[str, Any]
    tail_ms: float = 0.0
    fingerprint_ms: float = 0.0


@dataclass
class _TimedFingerprint:
    value: str
    ms: float = field(default=0.0)


class EnvelopeAssembler:
    """Собирает payload baseline/tail для режимов гидрации и инкрементального."""

    def __init__(self, history_builder: HistoryBuilder) -> None:
        self._history_builder = history_builder

    def _build_tail(self, session: Any, prompt: list[dict]) -> tuple[list[LLMMessage], float]:
        """Собрать tail из истории сессии (источник истины) — 4.D1.

        session.history уже содержит текущий промпт (добавлен обработчиком до
        пайплайна). System-сообщения принадлежат baseline и исключаются.
        Fallback на prompt — только если history не list (не настоящая сессия).
        """
        tail_start = time.time()
        history = getattr(session, "history", None)
        if not isinstance(history, list):
            result = self._tail_from_prompt(prompt)
        else:
            messages = self._history_builder.build(history)
            result = [m for m in messages if m.role != "system"]
        tail_ms = (time.time() - tail_start) * 1000
        return result, tail_ms

    @staticmethod
    def _timed_fingerprint(messages: list[LLMMessage]) -> _TimedFingerprint:
        """Вычислить fingerprint baseline с замером длительности (/context last)."""
        fp_start = time.time()
        fingerprint = EpochManager.compute_baseline_fingerprint(messages)
        fingerprint_ms = (time.time() - fp_start) * 1000
        return _TimedFingerprint(value=fingerprint, ms=fingerprint_ms)

    @staticmethod
    def _tail_from_prompt(prompt: list[dict]) -> list[LLMMessage]:
        """Fallback: собрать tail из prompt-блоков (нет истории сессии)."""
        tail: list[LLMMessage] = []
        for block in prompt:
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    tail.append(LLMMessage(role="user", content=text))
        return tail

    async def build_hydration(
        self,
        session: Any,
        registry: ContextRegistryImpl,
        prompt: list[dict],
        session_id: Any,
    ) -> AssembledEnvelope:
        """Режим гидрации: baseline пересобирается каждый ход."""
        baseline_text = await registry.render_baseline()
        baseline: list[LLMMessage] = []
        if baseline_text:
            baseline.append(LLMMessage(role="system", content=baseline_text))

        fp = self._timed_fingerprint(baseline)

        tail, tail_ms = self._build_tail(session, prompt)

        reconcile_info: dict[str, Any] = {"state": "hydration", "epoch_broken": False}

        logger.debug(
            "context.build.hydration",
            session_id=session_id,
            baseline_messages=len(baseline),
            tail_messages=len(tail),
        )

        return AssembledEnvelope(
            baseline=baseline,
            baseline_fingerprint=fp.value,
            tail=tail,
            reconcile_info=reconcile_info,
            tail_ms=tail_ms,
            fingerprint_ms=fp.ms,
        )

    async def build_incremental(
        self,
        session: Any,
        ctx: _SessionContext,
        registry: ContextRegistryImpl,
        prompt: list[dict],
        session_id: Any,
    ) -> AssembledEnvelope:
        """Инкрементальный режим: baseline из эпохи, только дельты в tail."""
        ctx.epoch_manager.reset_turn_counter()

        tail, tail_ms = self._build_tail(session, prompt)

        if not ctx.epoch_manager.is_active:
            return await self._start_new_epoch(ctx, registry, tail, session_id, tail_ms)

        epoch = ctx.epoch_manager.current_epoch
        assert epoch is not None

        reconcile_result = await ctx.reconciler.reconcile(
            epoch,
            registry,
        )

        reconcile_info: dict[str, Any] = {
            "state": reconcile_result.state.value,
            "epoch_broken": reconcile_result.epoch_broken,
            "changed_sources": reconcile_result.updated_sources,
        }

        if reconcile_result.epoch_broken:
            new_baseline_text = await registry.render_baseline()
            new_baseline: list[LLMMessage] = []
            if new_baseline_text:
                new_baseline.append(LLMMessage(role="system", content=new_baseline_text))

            fp = self._timed_fingerprint(new_baseline)
            ctx.epoch_manager.break_epoch(new_baseline, fp.value)

            logger.info(
                "context.build.incremental.epoch_broken",
                session_id=session_id,
                changed_sources=reconcile_result.updated_sources,
            )

            return AssembledEnvelope(
                baseline=new_baseline,
                baseline_fingerprint=fp.value,
                tail=tail,
                reconcile_info=reconcile_info,
                tail_ms=tail_ms,
                fingerprint_ms=fp.ms,
            )

        if reconcile_result.state.value == "updated" and reconcile_result.new_tail_messages:
            tail = [*reconcile_result.new_tail_messages, *tail]

        epoch = ctx.epoch_manager.current_epoch
        assert epoch is not None
        baseline = list(epoch.baseline)
        baseline_fingerprint = epoch.baseline_fingerprint

        logger.debug(
            "context.build.incremental.stable",
            session_id=session_id,
            epoch_id=epoch.epoch_id,
            baseline_fingerprint=baseline_fingerprint,
            reconcile_state=reconcile_result.state.value,
        )

        return AssembledEnvelope(
            baseline=baseline,
            baseline_fingerprint=baseline_fingerprint,
            tail=tail,
            reconcile_info=reconcile_info,
            tail_ms=tail_ms,
            fingerprint_ms=0.0,
        )

    async def _start_new_epoch(
        self,
        ctx: _SessionContext,
        registry: ContextRegistryImpl,
        tail: list[LLMMessage],
        session_id: Any,
        tail_ms: float,
    ) -> AssembledEnvelope:
        """Создать новую эпоху с текущим baseline."""
        baseline_text = await registry.render_baseline()
        baseline: list[LLMMessage] = []
        if baseline_text:
            baseline.append(LLMMessage(role="system", content=baseline_text))

        fp = self._timed_fingerprint(baseline)
        ctx.epoch_manager.start_epoch(baseline, fp.value)
        await ctx.reconciler.snapshot(registry)

        reconcile_info: dict[str, Any] = {
            "state": "new_epoch",
            "epoch_broken": False,
            "changed_sources": [],
        }

        logger.info(
            "context.build.incremental.new_epoch",
            session_id=session_id,
            epoch_id=(
                ctx.epoch_manager.current_epoch.epoch_id
                if ctx.epoch_manager.current_epoch
                else None
            ),
            baseline_fingerprint=fp.value,
        )

        return AssembledEnvelope(
            baseline=baseline,
            baseline_fingerprint=fp.value,
            tail=tail,
            reconcile_info=reconcile_info,
            tail_ms=tail_ms,
            fingerprint_ms=fp.ms,
        )
