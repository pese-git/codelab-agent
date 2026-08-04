"""Baseline чтения текущего формата сессии (write-фаза, гейт D0.3).

Замороженная фикстура `session_v6.json` — снимок on-disk формата
(`SessionDocument.model_dump(mode="json")`, schema_version=6) ДО write-фазы (ADR-006).
Фаза D2 введёт новый формат + upgrade; этот тест гарантирует, что старые сессии
(v6) продолжают читаться без потерь. Ломается → миграция потеряла обратную совместимость.
"""

import json
from pathlib import Path

from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.storage.document import SessionDocument

FIXTURE = Path(__file__).parent / "fixtures" / "session_v6.json"


def _load_raw() -> dict:
    return json.loads(FIXTURE.read_text())


class TestSessionV6Readable:
    """Формат v6 десериализуется и маппится в домен без потери данных."""

    def test_fixture_is_v6(self) -> None:
        assert _load_raw()["schema_version"] == 6

    def test_model_validate_parses(self) -> None:
        state = SessionDocument.model_validate(_load_raw())
        assert state.session_id == "sess_fixture_v6"
        assert state.cwd == "/tmp/proj"
        assert state.config_values == {"model": "openai/gpt-4o", "_agent": "universal"}
        assert state.runtime_capabilities is not None
        assert state.runtime_capabilities.fs_read is True
        assert state.runtime_capabilities.terminal is True

    def test_maps_to_domain(self) -> None:
        state = SessionDocument.model_validate(_load_raw())
        session = SessionMapper.to_domain(state)

        assert str(session.id) == "sess_fixture_v6"
        assert session.config.cwd == "/tmp/proj"
        # tool_calls, plan переживают десериализацию + маппинг
        calls = session.tool_calls.get_all()
        assert len(calls) == 1
        assert calls[0].id == "call_001"
        assert calls[0].tool_name == "grep"
        steps = session.plan.get_steps()
        assert len(steps) == 1
        assert steps[0].content == "step 1"
        # capabilities переносятся в доменный SessionConfig
        assert session.config.runtime_capabilities is not None
        assert session.config.runtime_capabilities.fs_read is True
