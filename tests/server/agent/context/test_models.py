"""Unit тесты для моделей Context Manager.

Тестирует:
- PayloadEnvelope.to_messages()
- ContextSnapshot.diff()
- ContextEpoch.get_full_context()
- Базовые свойства frozen dataclass
"""

import pytest

from codelab.server.agent.context.models import (
    BudgetAllocation,
    BuildOptions,
    ChangeState,
    ContextConfig,
    ContextEpoch,
    ContextItem,
    ContextSnapshot,
    ContextType,
    PayloadEnvelope,
    ReconcileResult,
    SubagentResult,
    TaskProfile,
    TaskType,
)
from codelab.server.llm.models import LLMMessage


class TestPayloadEnvelope:
    """Тесты для PayloadEnvelope."""

    def test_to_messages_returns_baseline_plus_tail(self):
        """to_messages() возвращает [*baseline, *tail]."""
        baseline = [
            LLMMessage(role="system", content="System prompt"),
            LLMMessage(role="user", content="Stable context"),
        ]
        tail = [
            LLMMessage(role="user", content="Current question"),
            LLMMessage(role="assistant", content="Current answer"),
        ]
        envelope = PayloadEnvelope(
            baseline=baseline,
            tail=tail,
            baseline_fingerprint="abc123",
            token_count=100,
        )

        messages = envelope.to_messages()

        assert len(messages) == 4
        assert messages[0].role == "system"
        assert messages[0].content == "System prompt"
        assert messages[1].content == "Stable context"
        assert messages[2].content == "Current question"
        assert messages[3].content == "Current answer"

    def test_to_messages_empty_baseline(self):
        """to_messages() работает с пустым baseline."""
        tail = [LLMMessage(role="user", content="Hello")]
        envelope = PayloadEnvelope(baseline=[], tail=tail)

        messages = envelope.to_messages()

        assert len(messages) == 1
        assert messages[0].content == "Hello"

    def test_to_messages_empty_tail(self):
        """to_messages() работает с пустым tail."""
        baseline = [LLMMessage(role="system", content="System")]
        envelope = PayloadEnvelope(baseline=baseline, tail=[])

        messages = envelope.to_messages()

        assert len(messages) == 1
        assert messages[0].content == "System"

    def test_to_messages_both_empty(self):
        """to_messages() возвращает пустой список при пустых baseline и tail."""
        envelope = PayloadEnvelope(baseline=[], tail=[])

        messages = envelope.to_messages()

        assert messages == []

    def test_frozen_dataclass(self):
        """PayloadEnvelope — frozen dataclass."""
        envelope = PayloadEnvelope(baseline=[], tail=[])

        with pytest.raises(AttributeError):
            envelope.token_count = 100  # type: ignore[misc]

    def test_defaults(self):
        """PayloadEnvelope имеет дефолтные значения."""
        envelope = PayloadEnvelope(baseline=[], tail=[])

        assert envelope.baseline_fingerprint == ""
        assert envelope.token_count == 0


class TestContextSnapshot:
    """Тесты для ContextSnapshot."""

    def test_diff_detects_changes(self):
        """diff() обнаруживает изменённые источники."""
        snapshot1 = ContextSnapshot(fingerprints={
            "source_a": "hash_a_v1",
            "source_b": "hash_b_v1",
            "source_c": "hash_c_v1",
        })
        snapshot2 = ContextSnapshot(fingerprints={
            "source_a": "hash_a_v1",
            "source_b": "hash_b_v2",
            "source_c": "hash_c_v1",
        })

        changed = snapshot1.diff(snapshot2)

        assert changed == ["source_b"]

    def test_diff_detects_multiple_changes(self):
        """diff() обнаруживает несколько изменений."""
        snapshot1 = ContextSnapshot(fingerprints={
            "source_a": "hash_a_v1",
            "source_b": "hash_b_v1",
        })
        snapshot2 = ContextSnapshot(fingerprints={
            "source_a": "hash_a_v2",
            "source_b": "hash_b_v2",
        })

        changed = snapshot1.diff(snapshot2)

        assert set(changed) == {"source_a", "source_b"}

    def test_diff_no_changes(self):
        """diff() возвращает пустой список при отсутствии изменений."""
        snapshot1 = ContextSnapshot(fingerprints={
            "source_a": "hash_a_v1",
            "source_b": "hash_b_v1",
        })
        snapshot2 = ContextSnapshot(fingerprints={
            "source_a": "hash_a_v1",
            "source_b": "hash_b_v1",
        })

        changed = snapshot1.diff(snapshot2)

        assert changed == []

    def test_diff_detects_new_source(self):
        """diff() обнаруживает новые источники."""
        snapshot1 = ContextSnapshot(fingerprints={
            "source_a": "hash_a_v1",
        })
        snapshot2 = ContextSnapshot(fingerprints={
            "source_a": "hash_a_v1",
            "source_b": "hash_b_v1",
        })

        changed = snapshot1.diff(snapshot2)

        assert changed == ["source_b"]

    def test_diff_detects_removed_source(self):
        """diff() не обнаруживает удалённые источники (только изменения)."""
        snapshot1 = ContextSnapshot(fingerprints={
            "source_a": "hash_a_v1",
            "source_b": "hash_b_v1",
        })
        snapshot2 = ContextSnapshot(fingerprints={
            "source_a": "hash_a_v1",
        })

        changed = snapshot1.diff(snapshot2)

        assert changed == []

    def test_diff_empty_snapshots(self):
        """diff() работает с пустыми снимками."""
        snapshot1 = ContextSnapshot(fingerprints={})
        snapshot2 = ContextSnapshot(fingerprints={})

        changed = snapshot1.diff(snapshot2)

        assert changed == []


class TestContextEpoch:
    """Тесты для ContextEpoch."""

    def test_get_full_context(self):
        """get_full_context() возвращает [*baseline, *mid_conversation_messages]."""
        baseline = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="Stable"),
        ]
        mid = [
            LLMMessage(role="user", content="Question 1"),
            LLMMessage(role="assistant", content="Answer 1"),
        ]
        epoch = ContextEpoch(
            epoch_id="epoch_1",
            baseline=baseline,
            baseline_fingerprint="fp_1",
            mid_conversation_messages=mid,
        )

        full = epoch.get_full_context()

        assert len(full) == 4
        assert full[0].content == "System"
        assert full[1].content == "Stable"
        assert full[2].content == "Question 1"
        assert full[3].content == "Answer 1"

    def test_get_full_context_empty_mid(self):
        """get_full_context() работает с пустым mid_conversation_messages."""
        baseline = [LLMMessage(role="system", content="System")]
        epoch = ContextEpoch(
            epoch_id="epoch_1",
            baseline=baseline,
            baseline_fingerprint="fp_1",
        )

        full = epoch.get_full_context()

        assert len(full) == 1
        assert full[0].content == "System"


class TestEnums:
    """Тесты для перечислений."""

    def test_task_type_values(self):
        """TaskType имеет ожидаемые значения."""
        assert TaskType.BUG_FIX == "bug_fix"
        assert TaskType.FEATURE == "feature"
        assert TaskType.REFACTOR == "refactor"
        assert TaskType.ARCHITECTURE == "architecture"

    def test_context_type_values(self):
        """ContextType имеет ожидаемые значения."""
        assert ContextType.FILE_CONTENT == "file_content"
        assert ContextType.FILE_SKELETON == "file_skeleton"
        assert ContextType.TERMINAL_OUTPUT == "terminal_output"
        assert ContextType.AGENT_REPORT == "agent_report"

    def test_change_state_values(self):
        """ChangeState имеет ожидаемые значения."""
        assert ChangeState.UNCHANGED == "unchanged"
        assert ChangeState.UPDATED == "updated"
        assert ChangeState.DEFERRED == "deferred"


class TestDataModels:
    """Тесты для остальных моделей данных."""

    def test_task_profile_creation(self):
        """TaskProfile создаётся корректно."""
        profile = TaskProfile(
            task_type=TaskType.FEATURE,
            search_terms=["test", "feature"],
            target_modules=["src/test.py"],
            investigation_depth=2,
            needs_tests=True,
        )

        assert profile.task_type == TaskType.FEATURE
        assert profile.search_terms == ["test", "feature"]
        assert profile.investigation_depth == 2
        assert profile.needs_tests is True

    def test_budget_allocation_creation(self):
        """BudgetAllocation создаётся корректно."""
        allocation = BudgetAllocation(
            system_tokens=2000,
            history_tokens=5000,
            tool_output_tokens=2000,
            response_buffer_tokens=1000,
        )

        assert allocation.system_tokens == 2000
        assert allocation.history_tokens == 5000

    def test_build_options_defaults(self):
        """BuildOptions имеет None по умолчанию."""
        options = BuildOptions()

        assert options.incremental is None
        assert options.skeletonize is None
        assert options.max_files is None

    def test_build_options_override(self):
        """BuildOptions переопределяет значения."""
        options = BuildOptions(incremental=True, skeletonize=False, max_files=50)

        assert options.incremental is True
        assert options.skeletonize is False
        assert options.max_files == 50

    def test_context_config_defaults(self):
        """ContextConfig имеет корректные дефолты."""
        config = ContextConfig()

        assert config.enabled is False
        assert config.gather_enabled is True
        assert config.max_context_tokens == 128000
        assert config.reserved_tokens == 4096
        assert config.system_share == 0.20
        assert config.history_share == 0.50

    def test_context_item_creation(self):
        """ContextItem создаётся корректно."""
        item = ContextItem(
            id="src/test.py",
            type=ContextType.FILE_CONTENT,
            content="def test(): pass",
            priority=5,
            owner_scope="single",
            token_count=10,
        )

        assert item.id == "src/test.py"
        assert item.type == ContextType.FILE_CONTENT
        assert item.priority == 5
        assert item.last_accessed == 0.0

    def test_reconcile_result_creation(self):
        """ReconcileResult создаётся корректно."""
        result = ReconcileResult(
            state=ChangeState.UPDATED,
            updated_sources=["source_a"],
            new_tail_messages=[],
            epoch_broken=True,
        )

        assert result.state == ChangeState.UPDATED
        assert result.epoch_broken is True

    def test_subagent_result_creation(self):
        """SubagentResult создаётся корректно."""
        result = SubagentResult(
            summary="Task completed",
            token_count=100,
            source_scope="subagent_1",
        )

        assert result.summary == "Task completed"
        assert result.shared_items == []
