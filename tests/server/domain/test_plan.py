"""Unit тесты для domain PlanEntry и PlanMapper."""

from codelab.server.domain.plan import PlanEntry
from codelab.server.domain.value_objects import PlanPriority, PlanStatus
from codelab.server.mapping.plan_mapper import PlanMapper


class TestPlanEntry:
    def test_defaults(self) -> None:
        entry = PlanEntry(content="Do something")
        assert entry.content == "Do something"
        assert entry.priority is PlanPriority.MEDIUM
        assert entry.status is PlanStatus.PENDING

    def test_with_all_fields(self) -> None:
        entry = PlanEntry(
            content="Fix bug",
            priority=PlanPriority.HIGH,
            status=PlanStatus.IN_PROGRESS,
        )
        assert entry.content == "Fix bug"
        assert entry.priority is PlanPriority.HIGH
        assert entry.status is PlanStatus.IN_PROGRESS

    def test_frozen(self) -> None:
        import pytest

        entry = PlanEntry(content="test")
        with pytest.raises(AttributeError):
            entry.content = "other"  # type: ignore[misc]


class TestPlanMapper:
    def test_to_acp_empty(self) -> None:
        result = PlanMapper.to_acp([])
        assert result == []

    def test_to_acp_single(self) -> None:
        entries = [
            PlanEntry(
                content="Step 1",
                priority=PlanPriority.HIGH,
                status=PlanStatus.PENDING,
            )
        ]
        result = PlanMapper.to_acp(entries)
        assert result == [{"content": "Step 1", "priority": "high", "status": "pending"}]

    def test_to_acp_multiple(self) -> None:
        entries = [
            PlanEntry(content="Step 1"),
            PlanEntry(content="Step 2", priority=PlanPriority.LOW, status=PlanStatus.COMPLETED),
        ]
        result = PlanMapper.to_acp(entries)
        assert len(result) == 2
        assert result[0]["content"] == "Step 1"
        assert result[1]["status"] == "completed"

    def test_from_acp_empty(self) -> None:
        result = PlanMapper.from_acp([])
        assert result == []

    def test_from_acp_single(self) -> None:
        blocks = [{"content": "Step 1", "priority": "high", "status": "pending"}]
        result = PlanMapper.from_acp(blocks)
        assert len(result) == 1
        assert result[0].content == "Step 1"
        assert result[0].priority is PlanPriority.HIGH
        assert result[0].status is PlanStatus.PENDING

    def test_from_acp_invalid_priority_defaults(self) -> None:
        blocks = [{"content": "Step 1", "priority": "invalid", "status": "pending"}]
        result = PlanMapper.from_acp(blocks)
        assert result[0].priority is PlanPriority.MEDIUM

    def test_from_acp_invalid_status_defaults(self) -> None:
        blocks = [{"content": "Step 1", "priority": "high", "status": "invalid"}]
        result = PlanMapper.from_acp(blocks)
        assert result[0].status is PlanStatus.PENDING

    def test_from_acp_logs_coerced_values(self) -> None:
        """Замена невалидного значения дефолтом не должна быть молчаливой."""
        import structlog

        blocks = [{"content": "Step 1", "priority": "urgent", "status": "skipped"}]
        with structlog.testing.capture_logs() as logs:
            PlanMapper.from_acp(blocks)

        events = {log["event"] for log in logs}
        assert "plan_entry_priority_coerced" in events
        assert "plan_entry_status_coerced" in events

    def test_round_trip(self) -> None:
        original = [
            PlanEntry(content="Step 1", priority=PlanPriority.HIGH, status=PlanStatus.PENDING),
            PlanEntry(content="Step 2", priority=PlanPriority.LOW, status=PlanStatus.COMPLETED),
        ]
        acp = PlanMapper.to_acp(original)
        restored = PlanMapper.from_acp(acp)
        assert len(restored) == len(original)
        assert restored[0].content == original[0].content
        assert restored[0].priority == original[0].priority
        assert restored[1].status == original[1].status


class TestEntriesToAcp:
    """Смешанный план (домен / wire-DTO / dict) → ACP-записи."""

    def test_domain_entry(self) -> None:
        result = PlanMapper.entries_to_acp(
            [PlanEntry(content="Step", priority=PlanPriority.LOW, status=PlanStatus.COMPLETED)]
        )
        assert result == [{"content": "Step", "priority": "low", "status": "completed"}]

    def test_acp_dict_passes_through(self) -> None:
        entry = {"content": "Step", "priority": "high", "status": "in_progress"}
        assert PlanMapper.entries_to_acp([entry]) == [entry]

    def test_pydantic_model_normalized_to_acp(self) -> None:
        from codelab.server.models import PlanStep

        result = PlanMapper.entries_to_acp([PlanStep(description="Step", status="completed")])
        assert result == [{"content": "Step", "priority": "medium", "status": "completed"}]

    def test_dict_missing_fields_gets_acp_defaults(self) -> None:
        result = PlanMapper.entries_to_acp([{"title": "Step"}])
        assert result == [{"content": "Step", "priority": "medium", "status": "pending"}]

    def test_invalid_values_replaced_by_defaults(self) -> None:
        result = PlanMapper.entries_to_acp([{"content": "S", "priority": "x", "status": "y"}])
        assert result == [{"content": "S", "priority": "medium", "status": "pending"}]

    def test_unknown_type_dropped_with_warning(self) -> None:
        import structlog

        with structlog.testing.capture_logs() as logs:
            result = PlanMapper.entries_to_acp(["not an entry"])

        assert result == []
        assert any(log["event"] == "plan_entry_dropped_unknown_type" for log in logs)

    def test_mixed_preserves_order(self) -> None:
        result = PlanMapper.entries_to_acp(
            [{"content": "first", "priority": "high", "status": "pending"}, PlanEntry("second")]
        )
        assert [entry["content"] for entry in result] == ["first", "second"]
