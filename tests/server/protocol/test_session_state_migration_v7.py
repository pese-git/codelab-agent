"""Round-trip тест миграции schema_version 6 → 7 (ADR-005 Фаза 4).

Change acp-independent-agent-core: parent_session_id становится
first-class полем SessionState. До v7 хранился в config_values
(см. context/child_session.py:84). При загрузке старой сессии значение
поднимается в first-class поле и удаляется из config_values.
"""

from __future__ import annotations

from codelab.server.protocol.state import SessionState


def test_v6_to_v7_migration_promotes_parent_session_id() -> None:
    """v6: parent_session_id в config_values. v7: first-class поле."""
    legacy_data = {
        "session_id": "sess_parent_1",
        "cwd": "/tmp",
        "config_values": {"parent_session_id": "sess_root", "_agent": "primary"},
        "schema_version": 6,
    }
    state = SessionState.model_validate(legacy_data)
    assert state.parent_session_id == "sess_root", (
        "parent_session_id должен подняться из config_values в first-class"
    )
    assert "parent_session_id" not in state.config_values, (
        "parent_session_id должен удалиться из config_values после миграции"
    )
    assert state.config_values == {"_agent": "primary"}, (
        "прочие config_values не должны быть затронуты"
    )
    assert state.schema_version == 7


def test_v7_round_trip_preserves_parent_session_id() -> None:
    """v7: parent_session_id в first-class поле сохраняется через save/load."""
    original = SessionState(
        session_id="sess_child_1",
        cwd="/tmp",
        parent_session_id="sess_root",
    )
    dumped = original.model_dump(mode="json")
    assert dumped["parent_session_id"] == "sess_root"
    loaded = SessionState.model_validate(dumped)
    assert loaded.parent_session_id == "sess_root"
    assert loaded.schema_version == 7


def test_v7_default_parent_session_id_is_none() -> None:
    state = SessionState(session_id="sess_1", cwd="/tmp")
    assert state.parent_session_id is None


def test_v6_migration_idempotent_when_field_already_set() -> None:
    """v6 → v7: если first-class поле уже заполнено, не перезаписываем."""
    legacy_data = {
        "session_id": "sess_1",
        "cwd": "/tmp",
        "parent_session_id": "sess_already_set",
        "config_values": {"parent_session_id": "sess_legacy"},
        "schema_version": 6,
    }
    state = SessionState.model_validate(legacy_data)
    assert state.parent_session_id == "sess_already_set", (
        "first-class поле имеет приоритет над legacy config_values"
    )
