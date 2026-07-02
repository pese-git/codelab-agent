"""Unit-тесты для session_set_mode handler.

Тестирует:
- Валидация modeId (valid, invalid, old-mode normalization)
- current_mode_update notification
- Session not found
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from codelab.server.protocol.handlers.config import session_set_mode
from codelab.server.protocol.state import SessionState


def _make_storage(session: SessionState | None = None):
    """Создать mock storage с опциональной сессией."""
    storage = AsyncMock()
    if session is not None:
        storage.load_session = AsyncMock(return_value=session)
        storage.save_session = AsyncMock()
    else:
        storage.load_session = AsyncMock(return_value=None)
    return storage


def _make_config_specs():
    """Создать config_specs с mode опцией."""
    return {
        "mode": {
            "id": "mode",
            "name": "Mode",
            "category": "mode",
            "type": "select",
            "default": "standard",
            "options": [
                {"value": "plan", "name": "Plan"},
                {"value": "standard", "name": "Standard"},
                {"value": "bypass", "name": "Bypass"},
            ],
        },
    }


class TestSessionSetModeValidModes:
    """Тесты установки валидных mode."""

    @pytest.mark.asyncio
    async def test_set_mode_plan(self) -> None:
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        storage = _make_storage(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "plan"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert session.config_values.get("mode") == "plan"
        # Проверяем current_mode_update через session/update
        mode_update = next(
            (
                n
                for n in outcome.notifications
                if n.method == "session/update"
                and n.params is not None
                and n.params.get("update", {}).get("sessionUpdate")
                == "current_mode_update"
            ),
            None,
        )
        assert mode_update is not None
        assert mode_update.params["update"]["currentModeId"] == "plan"

    @pytest.mark.asyncio
    async def test_set_mode_standard(self) -> None:
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        storage = _make_storage(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "standard"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert session.config_values.get("mode") == "standard"

    @pytest.mark.asyncio
    async def test_set_mode_bypass(self) -> None:
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        storage = _make_storage(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "bypass"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert session.config_values.get("mode") == "bypass"


class TestSessionSetModeOldModeNormalization:
    """Тесты нормализации старых mode значений."""

    @pytest.mark.asyncio
    async def test_old_mode_ask_normalizes_to_standard(self) -> None:
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        storage = _make_storage(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "ask"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert session.config_values.get("mode") == "standard"
        # Проверяем current_mode_update через session/update
        mode_update = next(
            (
                n
                for n in outcome.notifications
                if n.method == "session/update"
                and n.params is not None
                and n.params.get("update", {}).get("sessionUpdate")
                == "current_mode_update"
            ),
            None,
        )
        assert mode_update is not None
        assert mode_update.params["update"]["currentModeId"] == "standard"

    @pytest.mark.asyncio
    async def test_old_mode_code_normalizes_to_bypass(self) -> None:
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        storage = _make_storage(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "code"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert session.config_values.get("mode") == "bypass"

    @pytest.mark.asyncio
    async def test_old_mode_architect_normalizes_to_plan(self) -> None:
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        storage = _make_storage(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "architect"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert session.config_values.get("mode") == "plan"

    @pytest.mark.asyncio
    async def test_old_mode_debug_normalizes_to_standard(self) -> None:
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        storage = _make_storage(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "debug"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is None
        assert session.config_values.get("mode") == "standard"


class TestSessionSetModeInvalid:
    """Тесты невалидных modeId."""

    @pytest.mark.asyncio
    async def test_invalid_mode_id(self) -> None:
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        storage = _make_storage(session)
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "unknown_mode"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32602
        assert "modeId must be one of" in outcome.response.error.message

    @pytest.mark.asyncio
    async def test_missing_session_id(self) -> None:
        storage = _make_storage()
        outcome = await session_set_mode(
            "req_1",
            {"modeId": "plan"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32602

    @pytest.mark.asyncio
    async def test_missing_mode_id(self) -> None:
        storage = _make_storage()
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32602

    @pytest.mark.asyncio
    async def test_session_not_found(self) -> None:
        storage = _make_storage()
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "nonexistent", "modeId": "plan"},
            storage,
            _make_config_specs(),
        )
        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32001
        assert "Session not found" in outcome.response.error.message
