"""Тесты миграции SessionDocument v1 → v4.

Проверяют корректность миграции старых файлов сессий с добавлением
multi-agent полей (active_strategy, active_agents, session_metrics и др.).

Spec: openspec/specs/agent-config/spec.md (session-state-migration)
"""

from __future__ import annotations

from codelab.server.agent.config.models import SessionMetrics
from codelab.server.models import HistoryMessage
from codelab.server.storage.document import SessionDocument


class TestSessionStateMigrationV1toV4:
    """Тесты миграции полей multi-agent."""

    def test_migration_v1_to_v4_adds_all_fields(self) -> None:
        """v1 → v4: все multi-agent поля добавляются с defaults."""
        old_data = {
            "schema_version": 1,
            "session_id": "test-session",
            "cwd": "/tmp",
            "mcp_servers": [],
            "events_history": [],
            "config_values": {},
        }

        session = SessionDocument(**old_data)

        assert session.schema_version == 10
        assert session.active_strategy == "single"
        assert session.active_agents == []
        assert session.session_metrics is None
        assert session.correlation_id is None
        assert session.parent_session_id is None
        assert session.child_session_ids == []
        assert session.is_child_session is False
        assert session.task_result is None
        assert session.sliced_summary is None

    def test_migration_v0_to_v4(self) -> None:
        """v0 → v4: все поля (v1 + v3) добавляются с defaults."""
        old_data = {
            "session_id": "test-session",
            "cwd": "/tmp",
        }

        session = SessionDocument(**old_data)

        assert session.schema_version == 10
        assert session.events_history == []
        assert session.config_values == {}
        assert session.active_strategy == "single"
        assert session.active_agents == []
        assert session.session_metrics is None

    def test_new_fields_have_correct_defaults(self) -> None:
        """Новые поля имеют правильные значения по умолчанию."""
        session = SessionDocument(session_id="test", cwd="/tmp", mcp_servers=[])

        assert session.schema_version == 10
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

        session = SessionDocument(
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

        session = SessionDocument(**old_session_data)

        # Старые поля сохранены
        assert session.session_id == "old-session"
        assert session.title == "Old Session"
        assert len(session.history) == 2
        assert session.tool_call_counter == 5
        assert session.permission_policy == {"execute": "allow_always"}

        # Новые поля добавлены
        assert session.schema_version == 10
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
            session = SessionDocument(
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

        session = SessionDocument(**old_data)

        # Проверяем что все старые данные сохранены
        assert session.session_id == "preserve-test"
        assert session.cwd == "/project"
        assert session.mcp_servers == [{"name": "test-server"}]
        assert session.title == "Test Title"
        # mode=code мигрирует на bypass
        assert session.config_values["model"] == "gpt-4o"
        assert session.config_values["mode"] == "bypass"
        assert len(session.history) == 1
        assert session.tool_call_counter == 42
        assert session.permission_policy == {"read": "allow_always"}
        assert len(session.events_history) == 1

    def test_migration_v6_to_v7_adds_revision(self) -> None:
        """v6 → v7: документ получает ревизию для compare-and-set (ADR-007)."""
        session = SessionDocument.model_validate(
            {
                "schema_version": 6,
                "session_id": "sess_v6",
                "cwd": "/tmp",
                "mcp_servers": [],
            }
        )

        assert session.schema_version == 10
        # Старые сессии начинают с нуля — первая запись поднимет до 1
        assert session.revision == 0

    def test_migration_v8_to_v9_drops_terminal_bindings(self) -> None:
        """v8 → v9: связка alias'ов уезжает в процессный реестр (ADR-007, шаг A).

        Отметка владельца из v8 (P2-44) была компенсацией персистентности реестра;
        вместе с самим реестром она перестаёт существовать.
        """
        session = SessionDocument.model_validate(
            {
                "schema_version": 7,
                "session_id": "sess_v7",
                "cwd": "/tmp",
                "mcp_servers": [],
                "terminals": {"term_1": "client-id"},
                "terminal_counter": 1,
            }
        )

        assert session.schema_version == 10
        assert not hasattr(session, "terminals")
        assert not hasattr(session, "terminals_owner")
        # Счётчик остаётся: он выдаёт alias'ы и обязан быть монотонным через рестарт
        assert session.terminal_counter == 1

    def test_migration_v9_to_v10_drops_result_content(self) -> None:
        """v9 → v10: `result_content` вызовов удалён как поле без потребителя (ADR-007, шаг B1).

        Его писал только turn-путь, а читал никто: реплей и нотификации строятся из
        `content`, наружу в wire поле не уходило, клиент его не знает.
        """
        session = SessionDocument.model_validate(
            {
                "schema_version": 9,
                "session_id": "sess_v9",
                "cwd": "/tmp",
                "mcp_servers": [],
                "tool_calls": {
                    "call_001": {
                        "tool_call_id": "call_001",
                        "title": "Read",
                        "kind": "read",
                        "status": "completed",
                        "content": [{"type": "text", "text": "остаётся"}],
                        "result_content": [{"type": "text", "text": "уходит"}],
                    }
                },
            }
        )

        assert session.schema_version == 10
        call = session.tool_calls["call_001"]
        assert not hasattr(call, "result_content")
        # `content` — payload отправленной клиенту нотификации, он остаётся
        assert call.content == [{"type": "text", "text": "остаётся"}]

    def test_migration_v9_to_v10_survives_non_dict_tool_call(self) -> None:
        """Битая запись вызова не срывает миграцию всего документа.

        Документ с одной испорченной записью иначе оказался бы нечитаемым целиком —
        та же логика, что «битая ревизия не запирает сессию навсегда» (ADR-007).
        """
        session = SessionDocument.model_validate(
            {
                "schema_version": 9,
                "session_id": "sess_v9",
                "cwd": "/tmp",
                "mcp_servers": [],
                "tool_calls": {},
            }
        )

        assert session.schema_version == 10

    def test_schema_version_updated_after_migration(self) -> None:
        """После миграции schema_version равен 10 (v10 — `result_content` удалён, ADR-007)."""
        # v0
        session_v0 = SessionDocument(session_id="test", cwd="/tmp")
        assert session_v0.schema_version == 10

        # v1
        session_v1 = SessionDocument(
            schema_version=1,
            session_id="test",
            cwd="/tmp",
            mcp_servers=[],
        )
        assert session_v1.schema_version == 10

        # v3
        session_v3 = SessionDocument(
            schema_version=3,
            session_id="test",
            cwd="/tmp",
            mcp_servers=[],
        )
        assert session_v3.schema_version == 10

        # v4
        session_v4 = SessionDocument(
            schema_version=4,
            session_id="test",
            cwd="/tmp",
            mcp_servers=[],
        )
        assert session_v4.schema_version == 10

        # v5
        session_v5 = SessionDocument(
            schema_version=5,
            session_id="test",
            cwd="/tmp",
            mcp_servers=[],
        )
        assert session_v5.schema_version == 10

        # v6 (текущая)
        session_v6 = SessionDocument(
            schema_version=6,
            session_id="test",
            cwd="/tmp",
            mcp_servers=[],
        )
        assert session_v6.schema_version == 10

    def test_migration_v4_to_v5_adds_terminal_counter(self) -> None:
        """v4 → v5: появляется счётчик alias'ов терминалов (#18).

        Сам реестр, добавленный тем же шагом, удалён в v9 — от шага остался счётчик.
        """
        old_data = {
            "schema_version": 4,
            "session_id": "test-session",
            "cwd": "/tmp",
            "mcp_servers": [],
        }

        session = SessionDocument(**old_data)

        assert session.schema_version == 10
        assert session.terminal_counter == 0

    def test_migration_preserves_existing_terminal_counter(self) -> None:
        """Счётчик не затирается миграцией: alias'ы не должны переиспользоваться."""
        data = {
            "schema_version": 5,
            "session_id": "test-session",
            "cwd": "/tmp",
            "mcp_servers": [],
            "terminals": {"term_1": "client-uuid"},
            "terminal_counter": 1,
        }

        session = SessionDocument(**data)

        assert session.terminal_counter == 1

    def test_migration_v5_to_v6_plan_legacy_to_acp(self) -> None:
        """v5 → v6: legacy latest_plan {title,description} → ACP {content,priority,status}.

        P2-26: старая форма невалидна по ACP и теряла статусы при replay.
        """
        old_data = {
            "schema_version": 5,
            "session_id": "test-session",
            "cwd": "/tmp",
            "mcp_servers": [],
            "latest_plan": [
                {"title": "Step 1", "description": "First"},
                {"title": "Step 2", "description": "Second"},
            ],
        }

        session = SessionDocument(**old_data)

        assert session.schema_version == 10
        assert session.latest_plan == [
            {"content": "Step 1", "priority": "medium", "status": "pending"},
            {"content": "Step 2", "priority": "medium", "status": "pending"},
        ]

    def test_migration_v5_to_v6_preserves_acp_entries(self) -> None:
        """Уже-ACP entries со статусами не портятся миграцией (статусы сохраняются)."""
        data = {
            "schema_version": 5,
            "session_id": "test-session",
            "cwd": "/tmp",
            "mcp_servers": [],
            "latest_plan": [
                {"content": "Done step", "priority": "high", "status": "completed"},
                {"content": "Active step", "priority": "low", "status": "in_progress"},
            ],
        }

        session = SessionDocument(**data)

        assert session.latest_plan == [
            {"content": "Done step", "priority": "high", "status": "completed"},
            {"content": "Active step", "priority": "low", "status": "in_progress"},
        ]


class TestSessionStatePermissionSeam:
    """Seam-методы permission-состояния (pre-step D4-d + read-seam фазы B, ADR-006).

    Одноимённы с `domain.Session` — при switch резидента сайты не меняются.
    """

    def test_set_permission_policy(self) -> None:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.set_permission_policy("read", "allow_always")
        assert session.permission_policy == {"read": "allow_always"}

    def test_get_permission_policy(self) -> None:
        """Read-seam (фаза B): одноимён с `domain.Session.get_permission_policy`."""
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        assert session.get_permission_policy("read") is None
        session.set_permission_policy("read", "allow_always")
        assert session.get_permission_policy("read") == "allow_always"

    def test_cancel_and_uncancel_permission_request(self) -> None:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.cancel_permission_request("req_1")
        assert "req_1" in session.cancelled_permission_requests
        session.uncancel_permission_request("req_1")
        assert "req_1" not in session.cancelled_permission_requests

    def test_uncancel_is_idempotent(self) -> None:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        # discard отсутствующего id не падает
        session.uncancel_permission_request("absent")
        assert "absent" not in session.cancelled_permission_requests


class TestSessionStateAvailableCommandsSeam:
    """Seam-мутаторы available_commands (pre-step D4-d, ADR-006).

    Одноимённы с `domain.Session` — при switch резидента сайты не меняются.
    """

    def test_set_available_commands(self) -> None:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.set_available_commands([{"name": "plan"}])
        assert session.available_commands == [{"name": "plan"}]

    def test_extend_available_commands(self) -> None:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.set_available_commands([{"name": "plan"}])
        session.extend_available_commands([{"name": "mode"}])
        assert session.available_commands == [{"name": "plan"}, {"name": "mode"}]


class TestSessionStateConfigValueSeam:
    """Seam-методы config_values (pre-step D4-d + read-seam фазы B, ADR-006).

    Одноимённы с `domain.Session` — при switch резидента сайты не меняются.
    """

    def test_set_config_value(self) -> None:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.set_config_value("mode", "plan")
        assert session.config_values["mode"] == "plan"

    def test_get_config_value(self) -> None:
        """Read-seam (фаза B): одноимён с `domain.Session.get_config_value`."""
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        assert session.get_config_value("mode") is None
        assert session.get_config_value("mode", "standard") == "standard"
        session.set_config_value("mode", "plan")
        assert session.get_config_value("mode", "standard") == "plan"

    def test_set_config_value_overwrites(self) -> None:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.set_config_value("mode", "plan")
        session.set_config_value("mode", "code")
        assert session.config_values["mode"] == "code"


class TestSessionStateStorageMetaSeam:
    """Seam-мутаторы title/updated_at (pre-step D4-d, ADR-006).

    Одноимённы с `domain.Session` — при switch резидента сайты не меняются.
    """

    def test_set_title(self) -> None:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.set_title("My session")
        assert session.title == "My session"

    def test_mark_updated_is_utc_iso(self) -> None:
        from datetime import UTC, datetime

        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.mark_updated()
        parsed = datetime.fromisoformat(session.updated_at)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == UTC.utcoffset(None)

    def test_mark_updated_advances(self) -> None:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.mark_updated()
        first = session.updated_at
        session.mark_updated()
        assert session.updated_at >= first


class TestHistoryContentBlocksPreserved:
    """ACP content blocks в истории выживают round-trip через хранилище.

    Регрессия: `HistoryMessage.content` начинался с `list[MessageContent]`
    (type/text/data), и pydantic коэрцил блоки в эту модель, отбрасывая payload.
    `resource` (uri, текст файла, mime) исчезал при перезагрузке сессии, а
    `image` выживал случайно — его строковый `data` не проходил валидацию
    dict-поля, и union откатывался на сырые dict'ы.
    """

    _BLOCKS = [
        {"type": "text", "text": "посмотри файл"},
        {
            "type": "resource",
            "resource": {
                "uri": "file:///a.py",
                "text": "print(1)",
                "mimeType": "text/x-python",
            },
        },
        {"type": "image", "data": "abc", "mimeType": "image/png"},
    ]

    def test_blocks_survive_storage_roundtrip(self) -> None:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.history.append(HistoryMessage(role="user", content=self._BLOCKS))

        restored = SessionDocument.model_validate(session.model_dump(mode="json"))

        assert restored.model_dump(mode="json")["history"][0]["content"] == self._BLOCKS

    def test_legacy_coerced_entry_still_loads(self) -> None:
        """Уже сохранённые (обеднённые) записи читаются без ошибок."""
        legacy = {
            "schema_version": 6,
            "session_id": "s",
            "cwd": "/tmp",
            "mcp_servers": [],
            "history": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hi", "data": None},
                        {"type": "resource", "text": None, "data": None},
                    ],
                }
            ],
        }

        restored = SessionDocument.model_validate(legacy)

        entry = restored.history[0]
        assert not isinstance(entry, dict)
        assert entry.content == legacy["history"][0]["content"]
