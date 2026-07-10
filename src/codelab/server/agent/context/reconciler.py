"""DefaultContextReconciler — реконсилятор контекста.

Слой B — Жизненный цикл (Phase 4).

DefaultContextReconciler:
- snapshot() — собирает Codec-отпечатки всех источников
- reconcile() — определяет изменения на безопасной границе хода
- Подписывается на InvalidationSignalBus для единого сигнала инвалидации
- Поддерживает состояния UNCHANGED / UPDATED / DEFERRED
- Консервативный fallback: неопределённое изменение → epoch_broken=True
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from codelab.server.agent.context.interfaces import (
    ContextReconciler,
    ContextRegistry,
)
from codelab.server.agent.context.models import (
    ChangeState,
    ContextEpoch,
    ContextSnapshot,
    ReconcileResult,
)

if TYPE_CHECKING:
    from codelab.server.llm.models import LLMMessage

logger = structlog.get_logger(__name__)

BASELINE_SOURCE_IDS = frozenset({"system_prompt", "skill_catalog"})


class DefaultContextReconciler(ContextReconciler):
    """Реконсилятор контекста с Codec-детектом изменений.

    Подписывается на InvalidationSignalBus для получения сигналов
    об изменении файлов. Использует двойную защиту: сигнал + Codec-сравнение.

    Attributes:
        _last_snapshot: Последний снимок отпечатков
        _pending_invalidations: Пути файлов, изменённых через сигнал
        _deferred_changes: Отложенные изменения (DEFERRED → следующая граница)
    """

    def __init__(self) -> None:
        self._last_snapshot: ContextSnapshot | None = None
        self._pending_invalidations: set[str] = set()
        self._deferred_changes: list[str] = []

    async def snapshot(self, registry: ContextRegistry) -> ContextSnapshot:
        """Собрать снимок отпечатков всех источников.

        Args:
            registry: Реестр источников контекста

        Returns:
            ContextSnapshot с fingerprints всех источников
        """
        fingerprints: dict[str, str] = {}
        for source_id in registry.list_sources():
            source = registry.get_source(source_id)
            if source is not None:
                try:
                    fp = await source.fingerprint()
                    fingerprints[source_id] = fp
                except Exception:
                    logger.warning(
                        "reconciler.snapshot.fingerprint_failed",
                        source_id=source_id,
                    )
                    fingerprints[source_id] = ""

        snapshot = ContextSnapshot(fingerprints=fingerprints)
        self._last_snapshot = snapshot

        logger.debug(
            "reconciler.snapshot.created",
            sources_count=len(fingerprints),
        )

        return snapshot

    async def reconcile(
        self,
        epoch: ContextEpoch,
        registry: ContextRegistry,
    ) -> ReconcileResult:
        """Определить изменения на границе хода.

        Применяет изменения только на безопасной границе хода.
        Если изменение обнаружено в середине хода — DEFERRED.

        Args:
            epoch: Текущая контекстная эпоха
            registry: Реестр источников контекста

        Returns:
            ReconcileResult с состоянием и изменениями
        """
        if self._last_snapshot is None:
            await self.snapshot(registry)

        current_snapshot = await self._build_snapshot(registry)

        changed_sources = self._last_snapshot.diff(current_snapshot)

        all_changed = list(set(changed_sources) | self._pending_invalidations)
        all_changed.extend(self._deferred_changes)
        all_changed = sorted(set(all_changed))

        self._pending_invalidations.clear()
        self._deferred_changes.clear()

        if not all_changed:
            self._last_snapshot = current_snapshot
            logger.debug(
                "reconciler.reconcile.unchanged",
                epoch_id=epoch.epoch_id,
            )
            return ReconcileResult(
                state=ChangeState.UNCHANGED,
                updated_sources=[],
                new_tail_messages=[],
                epoch_broken=False,
            )

        baseline_changes = [s for s in all_changed if s in BASELINE_SOURCE_IDS]
        file_changes = [s for s in all_changed if s not in BASELINE_SOURCE_IDS]

        if baseline_changes:
            logger.info(
                "reconciler.reconcile.baseline_changed",
                epoch_id=epoch.epoch_id,
                changed_sources=baseline_changes,
            )
            self._last_snapshot = current_snapshot
            return ReconcileResult(
                state=ChangeState.UPDATED,
                updated_sources=all_changed,
                new_tail_messages=[],
                epoch_broken=True,
            )

        if file_changes:
            updates_text = await registry.render_updates(file_changes)
            new_tail: list[LLMMessage] = []
            if updates_text:
                from codelab.server.llm.models import LLMMessage

                new_tail.append(
                    LLMMessage(
                        role="system",
                        content=f"<context_updates>\n{updates_text}\n</context_updates>",
                    )
                )

            logger.info(
                "reconciler.reconcile.updated",
                epoch_id=epoch.epoch_id,
                changed_sources=file_changes,
                new_tail_messages=len(new_tail),
            )
            self._last_snapshot = current_snapshot
            return ReconcileResult(
                state=ChangeState.UPDATED,
                updated_sources=file_changes,
                new_tail_messages=new_tail,
                epoch_broken=False,
            )

        self._last_snapshot = current_snapshot
        return ReconcileResult(
            state=ChangeState.UNCHANGED,
            updated_sources=[],
            new_tail_messages=[],
            epoch_broken=False,
        )

    def on_file_invalidated(self, path: str) -> None:
        """Обработчик сигнала инвалидации файла.

        Вызывается из InvalidationSignalBus при fs/write.

        Args:
            path: Путь к изменённому файлу
        """
        self._pending_invalidations.add(path)
        logger.debug(
            "reconciler.file_invalidated",
            path=path,
            pending_count=len(self._pending_invalidations),
        )

    def defer_changes(self, source_ids: list[str]) -> None:
        """Отложить изменения до следующей безопасной границы.

        Args:
            source_ids: ID источников с изменениями
        """
        self._deferred_changes.extend(source_ids)
        logger.debug(
            "reconciler.changes_deferred",
            deferred_sources=source_ids,
            total_deferred=len(self._deferred_changes),
        )

    async def _build_snapshot(self, registry: ContextRegistry) -> ContextSnapshot:
        """Построить снимок без сохранения в _last_snapshot."""
        fingerprints: dict[str, str] = {}
        for source_id in registry.list_sources():
            source = registry.get_source(source_id)
            if source is not None:
                try:
                    fp = await source.fingerprint()
                    fingerprints[source_id] = fp
                except Exception:
                    logger.warning(
                        "reconciler.build_snapshot.fingerprint_failed",
                        source_id=source_id,
                    )
                    fingerprints[source_id] = ""

        return ContextSnapshot(fingerprints=fingerprints)

    def reset(self) -> None:
        """Сбросить состояние реконсилиатора."""
        self._last_snapshot = None
        self._pending_invalidations.clear()
        self._deferred_changes.clear()
        logger.debug("reconciler.reset")
