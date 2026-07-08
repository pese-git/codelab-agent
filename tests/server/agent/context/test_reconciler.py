"""Unit тесты для DefaultContextReconciler.

Тестирует:
- snapshot() — сбор отпечатков
- reconcile() — UNCHANGED / UPDATED / DEFERRED
- on_file_invalidated() — единый сигнал инвалидации
- defer_changes() — отложенные изменения
- Консервативный fallback при неопределённом изменении
"""

import pytest

from codelab.server.agent.context.models import (
    ChangeState,
    ContextEpoch,
    ContextSnapshot,
)
from codelab.server.agent.context.reconciler import DefaultContextReconciler
from codelab.server.agent.context.registry import (
    ContextRegistryImpl,
    FileContextSource,
)
from codelab.server.llm.models import LLMMessage


def _make_epoch(
    epoch_id: str = "test-epoch",
    baseline: list[LLMMessage] | None = None,
    fingerprint: str = "fp1",
) -> ContextEpoch:
    return ContextEpoch(
        epoch_id=epoch_id,
        baseline=baseline or [LLMMessage(role="system", content="baseline")],
        baseline_fingerprint=fingerprint,
    )


def _make_registry(
    sources: dict[str, str] | None = None,
) -> ContextRegistryImpl:
    registry = ContextRegistryImpl()
    for path, content in (sources or {}).items():
        registry.register(FileContextSource(path, content))
    return registry


class TestReconcilerSnapshot:
    """Тесты snapshot()."""

    async def test_snapshot_collects_fingerprints(self):
        """snapshot() собирает fingerprints всех источников."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file_a.py": "content_a", "file_b.py": "content_b"})

        snapshot = await reconciler.snapshot(registry)

        assert "file_a.py" in snapshot.fingerprints
        assert "file_b.py" in snapshot.fingerprints
        assert snapshot.fingerprints["file_a.py"] != ""

    async def test_snapshot_empty_registry(self):
        """snapshot() на пустом реестре — пустой fingerprint dict."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry()

        snapshot = await reconciler.snapshot(registry)

        assert snapshot.fingerprints == {}


class TestReconcilerReconcile:
    """Тесты reconcile()."""

    async def test_reconcile_unchanged_when_no_changes(self):
        """UNCHANGED когда ни один источник не изменился."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file.py": "content"})
        await reconciler.snapshot(registry)
        epoch = _make_epoch()

        result = await reconciler.reconcile(epoch, registry)

        assert result.state == ChangeState.UNCHANGED
        assert result.epoch_broken is False
        assert result.updated_sources == []

    async def test_reconcile_updated_when_file_changed(self):
        """UPDATED когда файл изменился (не baseline-источник)."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file.py": "old_content"})
        await reconciler.snapshot(registry)

        registry.register(FileContextSource("file.py", "new_content"))
        epoch = _make_epoch()

        result = await reconciler.reconcile(epoch, registry)

        assert result.state == ChangeState.UPDATED
        assert "file.py" in result.updated_sources
        assert result.epoch_broken is False

    async def test_reconcile_epoch_broken_when_system_prompt_changed(self):
        """epoch_broken=True когда изменился system_prompt (baseline-источник)."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"system_prompt": "old system"})
        await reconciler.snapshot(registry)

        registry.register(FileContextSource("system_prompt", "new system"))
        epoch = _make_epoch()

        result = await reconciler.reconcile(epoch, registry)

        assert result.state == ChangeState.UPDATED
        assert result.epoch_broken is True
        assert "system_prompt" in result.updated_sources

    async def test_reconcile_epoch_broken_when_skill_catalog_changed(self):
        """epoch_broken=True когда изменился skill_catalog (baseline-источник)."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"skill_catalog": "old catalog"})
        await reconciler.snapshot(registry)

        registry.register(FileContextSource("skill_catalog", "new catalog"))
        epoch = _make_epoch()

        result = await reconciler.reconcile(epoch, registry)

        assert result.state == ChangeState.UPDATED
        assert result.epoch_broken is True

    async def test_reconcile_updated_generates_tail_messages(self):
        """UPDATED для файловых изменений генерирует new_tail_messages."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file.py": "old"})
        await reconciler.snapshot(registry)

        registry.register(FileContextSource("file.py", "new"))
        epoch = _make_epoch()

        result = await reconciler.reconcile(epoch, registry)

        assert len(result.new_tail_messages) > 0
        assert "context_updates" in result.new_tail_messages[0].content

    async def test_reconcile_no_snapshot_creates_one(self):
        """reconcile без предварительного snapshot создаёт его автоматически."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file.py": "content"})
        epoch = _make_epoch()

        result = await reconciler.reconcile(epoch, registry)

        assert result.state == ChangeState.UNCHANGED


class TestReconcilerInvalidationSignal:
    """Тесты единого сигнала инвалидации."""

    async def test_on_file_invalidated_detected_by_reconcile(self):
        """on_file_invalidated → reconcile обнаруживает изменение."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file.py": "content"})
        await reconciler.snapshot(registry)

        reconciler.on_file_invalidated("file.py")
        epoch = _make_epoch()

        result = await reconciler.reconcile(epoch, registry)

        assert "file.py" in result.updated_sources

    async def test_invalidated_signal_cleared_after_reconcile(self):
        """Сигнал инвалидации очищается после reconcile."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file.py": "content"})
        await reconciler.snapshot(registry)

        reconciler.on_file_invalidated("file.py")
        epoch = _make_epoch()
        await reconciler.reconcile(epoch, registry)

        result = await reconciler.reconcile(epoch, registry)
        assert result.state == ChangeState.UNCHANGED

    async def test_double_detection_signal_and_codec(self):
        """Двойная защита: сигнал + Codec-сравнение дают одинаковый результат."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file.py": "old"})
        await reconciler.snapshot(registry)

        registry.register(FileContextSource("file.py", "new"))
        reconciler.on_file_invalidated("file.py")
        epoch = _make_epoch()

        result = await reconciler.reconcile(epoch, registry)

        assert "file.py" in result.updated_sources


class TestReconcilerDefer:
    """Тесты отложенных изменений."""

    async def test_deferred_changes_applied_on_next_reconcile(self):
        """defer_changes → применяются на следующем reconcile."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file.py": "content"})
        await reconciler.snapshot(registry)

        reconciler.defer_changes(["file.py"])
        epoch = _make_epoch()

        result = await reconciler.reconcile(epoch, registry)

        assert "file.py" in result.updated_sources

    async def test_deferred_cleared_after_reconcile(self):
        """Отложенные изменения очищаются после reconcile."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file.py": "content"})
        await reconciler.snapshot(registry)

        reconciler.defer_changes(["file.py"])
        epoch = _make_epoch()
        await reconciler.reconcile(epoch, registry)

        result = await reconciler.reconcile(epoch, registry)
        assert result.state == ChangeState.UNCHANGED


class TestReconcilerReset:
    """Тесты сброса состояния."""

    async def test_reset_clears_all_state(self):
        """reset() очищает snapshot, invalidations, deferred."""
        reconciler = DefaultContextReconciler()
        registry = _make_registry({"file.py": "content"})
        await reconciler.snapshot(registry)
        reconciler.on_file_invalidated("file.py")
        reconciler.defer_changes(["other.py"])

        reconciler.reset()

        assert reconciler._last_snapshot is None
        assert len(reconciler._pending_invalidations) == 0
        assert len(reconciler._deferred_changes) == 0
