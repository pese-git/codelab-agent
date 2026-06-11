"""Тесты миграции SessionState v1 → v3.

Проверяют корректность миграции старых файлов сессий с добавлением
multi-agent полей (active_strategy, active_agents, session_metrics и др.).

Spec: openspec/specs/agent-config/spec.md (session-state-migration)
"""

from __future__ import annotations

from codelab.server.agent.config.models import SessionMetrics
from codelab.server.protocol.state import SessionState


class TestSessionStateMigrationV1toV3:
    """Тесты миграции полей multi-agent."""

    def test_migration_v1_to_v3_adds_all_fields(self) -> None:
        """v1 → v3: все multi-agent поля добавляются с defaults."""
        old_data = {
            "schema_version": 1,
            "session_id": "test-session",
            "cwd": "/tmp",
            "mcp_servers": [],
            "events_history": [],
            "config_values": {},
        }

        session = SessionState(**old_data)

        assert session.schema_version == 3
        assert session.active_strategy == "single"
        assert session.active_agents == []
        assert session.session_metrics is None
        assert session.correlation_id is None
        assert session.parent_session_id is None
        assert session.child_session_ids == []
        assert session.is_child_session is False
        assert session.task_result is None
        assert session.sliced_summary is None

    def test_migration_v0_to_v3(self) -> None:
        """v0 → v3: все поля (v1 + v3) добавляются с defaults."""
        old_data = {
            "session_id": "test-session",
            "cwd": "/tmp",
        }

        session = SessionState(**old_data)

        assert session.schema_version == 3
        assert session.events_history == []
        assert session.config_values == {}
        assert session.active_strategy == "single"
        assert session.active_agents == []
        assert session.session_metrics is None

    def test_new_fields_have_correct_defaults(self) -> None:
        """Новые поля имеют правильные значения по умолчанию."""
        session = SessionState(session_id="test", cwd="/tmp", mcp_servers=[])

        assert session.active_strategy == "single"
        assert session.active_agents == []
        assert session.session_metrics is None
        assert session.correlation_id is None
        assert session.parent_session_id is None
        assert session.child_session_ids == []
        assert session.is_child_session is False
        assert session.task_result is None
        assert session.sliced_summary is None

    def test_explicit_multi_agent_values(self) -> None:
        """Можно явно задать multi-agent значения."""
        metrics = SessionMetrics(
            total_time_sec=10.5,
            total_llm_calls=3,
            input_tokens=1000,
            output_tokens=500,
        )

        session = SessionState(
            session_id="test",
            cwd="/tmp",
            mcp_servers=[],
            active_strategy="multi_orchestrated",
            active_agents=["coder", "reviewer"],
            session_metrics=metrics,
            correlation_id="corr-123",
            parent_session_id="parent-456",
            child_session_ids=["child-1", "child-2"],
            is_child_session=True,
            task_result="Task completed",
            sliced_summary="Summary of subagent response",
        )

        assert session.active_strategy == "multi_orchestrated"
        assert session.active_agents == ["coder", "reviewer"]
        assert session.session_metrics is not None
        assert session.session_metrics.total_llm_calls == 3
        assert session.correlation_id == "corr-123"
        assert session.parent_session_id == "parent-456"
        assert session.child_session_ids == ["child-1", "child-2"]
        assert session.is_child_session is True
        assert session.task_result == "Task completed"
        assert session.sliced_summary == "Summary of subagent response"

    def test_backward_compatibility_with_existing_sessions(self) -> None:
        """Старые сессии (v1) загружаются без ошибок."""
        old_session_data = {
            "schema_version": 1,
            "session_id": "old-session",
            "cwd": "/home/user/project",
            "mcp_servers": [{"name": "fs"}],
            "title": "Old Session",
            "updated_at": "2026-06-01T10:00:00",
            "config_values": {"mode": "code"},
            "history": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
            "tool_call_counter": 5,
            "tool_calls": {},
            "permission_policy": {"execute": "allow_always"},
            "events_history": [{"type": "session/update"}],
        }

        session = SessionState(**old_session_data)

        # Старые поля сохранены
        assert session.session_id == "old-session"
        assert session.title == "Old Session"
        assert len(session.history) == 2
        assert session.tool_call_counter == 5
        assert session.permission_policy == {"execute": "allow_always"}

        # Новые поля добавлены
        assert session.schema_version == 3
        assert session.active_strategy == "single"
        assert session.active_agents == []
        assert session.session_metrics is None

    def test_active_strategy_valid_values(self) -> None:
        """active_strategy принимает допустимые значения стратегий."""
        valid_strategies = [
            "single",
            "multi_orchestrated",
            "multi_choreographed",
            "hierarchical",
        ]

        for strategy in valid_strategies:
            session = SessionState(
                session_id="test",
                cwd="/tmp",
                mcp_servers=[],
                active_strategy=strategy,
            )
            assert session.active_strategy == strategy

    def test_migration_preserves_existing_data(self) -> None:
        """Миграция не теряет существующие данные."""
        old_data = {
            "schema_version": 1,
            "session_id": "preserve-test",
            "cwd": "/project",
            "mcp_servers": [{"name": "test-server"}],
            "title": "Test Title",
            "config_values": {"model": "gpt-4o", "mode": "code"},
            "history": [{"role": "user", "content": "test"}],
            "tool_call_counter": 42,
            "permission_policy": {"read": "allow_always"},
            "events_history": [{"event": "test"}],
        }

        session = SessionState(**old_data)

        # Проверяем что все старые данные сохранены
        assert session.session_id == "preserve-test"
        assert session.cwd == "/project"
        assert session.mcp_servers == [{"name": "test-server"}]
        assert session.title == "Test Title"
        assert session.config_values == {"model": "gpt-4o", "mode": "code"}
        assert len(session.history) == 1
        assert session.tool_call_counter == 42
        assert session.permission_policy == {"read": "allow_always"}
        assert len(session.events_history) == 1

    def test_schema_version_updated_after_migration(self) -> None:
        """После миграции schema_version равен 3."""
        # v0
        session_v0 = SessionState(session_id="test", cwd="/tmp")
        assert session_v0.schema_version == 3

        # v1
        session_v1 = SessionState(
            schema_version=1,
            session_id="test",
            cwd="/tmp",
            mcp_servers=[],
        )
        assert session_v1.schema_version == 3

        # v3 (текущая)
        session_v3 = SessionState(
            schema_version=3,
            session_id="test",
            cwd="/tmp",
            mcp_servers=[],
        )
        assert session_v3.schema_version == 3
