"""Интеграционные тесты для полного пути Фазы 4.

Тестирует:
- FileCacheDecorator → InvalidationSignalBus → DefaultContextReconciler
- FileContextSource.update_content() при сигнале инвалидации
- Инкрементальный режим с переиспользованием registry
- Полный путь: fs/write → invalidate → reconcile → epoch_broken
"""

from codelab.server.agent.context.epoch import EpochManager
from codelab.server.agent.context.file_cache import (
    InMemoryFileCache,
    InvalidationSignalBus,
)
from codelab.server.agent.context.file_cache_decorator import FileCacheDecorator
from codelab.server.agent.context.models import ChangeState
from codelab.server.agent.context.reconciler import DefaultContextReconciler
from codelab.server.agent.context.registry import (
    ContextRegistryImpl,
    FileContextSource,
)
from codelab.server.llm.models import LLMMessage
from codelab.server.tools.base import ToolExecutionResult


class MockToolExecutor:
    """Mock executor для тестирования FileCacheDecorator."""

    def __init__(self, read_content: str | None = None) -> None:
        self.read_content = read_content
        self.last_call: dict | None = None

    async def execute(self, session: object, arguments: dict) -> ToolExecutionResult:
        self.last_call = arguments
        operation = arguments.get("operation", "")

        if operation == "read" and self.read_content is not None:
            return ToolExecutionResult(
                success=True,
                output=self.read_content,
            )
        if operation == "write":
            return ToolExecutionResult(
                success=True,
                output="written",
            )
        return ToolExecutionResult(
            success=False,
            output=None,
        )


class MockSession:
    """Mock session для тестирования."""

    def __init__(self, session_id: str = "test-session") -> None:
        self.session_id = session_id


class TestFileCacheDecoratorIntegration:
    """Тесты интеграции FileCacheDecorator с InvalidationSignalBus."""

    async def test_fs_write_triggers_invalidation_signal(self):
        """fs/write → invalidate() → сигнал в InvalidationSignalBus."""
        signal_bus = InvalidationSignalBus()
        cache = InMemoryFileCache(signal_bus=signal_bus)
        executor = MockToolExecutor()
        decorator = FileCacheDecorator(executor, cache=cache)

        received_signals: list[str] = []
        signal_bus.subscribe(lambda path: received_signals.append(path))

        session = MockSession()
        await decorator.execute(
            session,
            {"operation": "write", "path": "test.py"},
        )

        assert "test.py" in received_signals

    async def test_fs_read_populates_cache(self):
        """fs/read → cache.set() → содержимое в кэше."""
        cache = InMemoryFileCache()
        executor = MockToolExecutor(read_content="file content")
        decorator = FileCacheDecorator(executor, cache=cache)

        session = MockSession()
        await decorator.execute(
            session,
            {"operation": "read", "path": "test.py"},
        )

        assert cache.get("test.py") == "file content"

    async def test_full_path_write_invalidate_reconcile(self):
        """Полный путь: fs/write → invalidate → reconcile обнаруживает изменение."""
        signal_bus = InvalidationSignalBus()
        cache = InMemoryFileCache(signal_bus=signal_bus)
        executor = MockToolExecutor()
        decorator = FileCacheDecorator(executor, cache=cache)

        reconciler = DefaultContextReconciler()
        signal_bus.subscribe(reconciler.on_file_invalidated)

        registry = ContextRegistryImpl()
        registry.register(FileContextSource("test.py", "old content"))
        await reconciler.snapshot(registry)

        session = MockSession()
        await decorator.execute(
            session,
            {"operation": "write", "path": "test.py"},
        )

        from codelab.server.agent.context.models import ContextEpoch

        epoch = ContextEpoch(
            epoch_id="test",
            baseline=[LLMMessage(role="system", content="baseline")],
            baseline_fingerprint="fp",
        )

        result = await reconciler.reconcile(epoch, registry)

        assert "test.py" in result.updated_sources


class TestFileContextSourceUpdate:
    """Тесты обновления FileContextSource."""

    async def test_update_content_changes_fingerprint(self):
        """update_content() изменяет fingerprint источника."""
        source = FileContextSource("test.py", "old content")
        old_fp = await source.fingerprint()

        source.update_content("new content")
        new_fp = await source.fingerprint()

        assert old_fp != new_fp

    async def test_update_content_changes_render(self):
        """update_content() изменяет результат render()."""
        source = FileContextSource("test.py", "old content")

        source.update_content("new content")

        assert await source.render() == "new content"


class TestIncrementalModeRegistryReuse:
    """Тесты переиспользования registry в инкрементальном режиме."""

    async def test_registry_reuse_preserves_sources(self):
        """Переиспользование registry сохраняет источники между ходами."""
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("file1.py", "content1"))
        registry.register(FileContextSource("file2.py", "content2"))

        sources_before = set(registry.list_sources())

        registry.register(FileContextSource("file1.py", "content1_updated"))

        sources_after = set(registry.list_sources())

        assert sources_before == sources_after
        source = registry.get_source("file1.py")
        assert source is not None
        assert await source.render() == "content1_updated"


class TestEpochManagerIntegration:
    """Тесты интеграции EpochManager с реконсилиатором."""

    async def test_epoch_break_on_baseline_change(self):
        """Изменение baseline-источника → epoch_broken=True."""
        reconciler = DefaultContextReconciler()
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("system_prompt", "old system"))
        await reconciler.snapshot(registry)

        registry.register(FileContextSource("system_prompt", "new system"))
        epoch = EpochManager.compute_baseline_fingerprint(
            [LLMMessage(role="system", content="old system")]
        )

        from codelab.server.agent.context.models import ContextEpoch

        context_epoch = ContextEpoch(
            epoch_id="test",
            baseline=[LLMMessage(role="system", content="old system")],
            baseline_fingerprint=epoch,
        )

        result = await reconciler.reconcile(context_epoch, registry)

        assert result.epoch_broken is True
        assert "system_prompt" in result.updated_sources

    async def test_stable_baseline_no_epoch_break(self):
        """Стабильный baseline → epoch_broken=False."""
        reconciler = DefaultContextReconciler()
        registry = ContextRegistryImpl()
        registry.register(FileContextSource("file.py", "content"))
        await reconciler.snapshot(registry)

        from codelab.server.agent.context.models import ContextEpoch

        epoch = ContextEpoch(
            epoch_id="test",
            baseline=[LLMMessage(role="system", content="baseline")],
            baseline_fingerprint="fp",
        )

        result = await reconciler.reconcile(epoch, registry)

        assert result.epoch_broken is False
        assert result.state == ChangeState.UNCHANGED
