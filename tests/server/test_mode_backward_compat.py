"""Integration-тесты backward compatibility для mode system.

Тестирует:
- SessionState migration с старыми mode значениями
- normalize_mode для всех старых значений
- Deprecation warnings при загрузке старых mode
"""

from __future__ import annotations

import logging

import pytest

from codelab.server.protocol.mode import (
    DEFAULT_MODE,
    MODE_BYPASS,
    MODE_PLAN,
    MODE_STANDARD,
    OLD_TO_NEW_MODE,
    VALID_MODES,
    normalize_mode,
)
from codelab.server.protocol.state import SessionState


class TestNormalizeModeBackwardCompat:
    """Тесты нормализации старых mode значений."""

    def test_all_old_modes_mapped(self) -> None:
        """Все старые mode должны быть в OLD_TO_NEW_MODE."""
        expected_old = {"ask", "code", "architect", "debug"}
        assert set(OLD_TO_NEW_MODE.keys()) == expected_old

    def test_all_new_modes_valid(self) -> None:
        """Все новые mode должны быть в VALID_MODES."""
        for new_mode in OLD_TO_NEW_MODE.values():
            assert new_mode in VALID_MODES

    def test_ask_to_standard(self) -> None:
        assert normalize_mode("ask") == MODE_STANDARD

    def test_code_to_bypass(self) -> None:
        assert normalize_mode("code") == MODE_BYPASS

    def test_architect_to_plan(self) -> None:
        assert normalize_mode("architect") == MODE_PLAN

    def test_debug_to_standard(self) -> None:
        assert normalize_mode("debug") == MODE_STANDARD

    def test_new_modes_unchanged(self) -> None:
        for mode in VALID_MODES:
            assert normalize_mode(mode) == mode

    def test_unknown_falls_back_to_default(self) -> None:
        assert normalize_mode("unknown") == DEFAULT_MODE
        assert normalize_mode("") == DEFAULT_MODE
        assert normalize_mode("foo") == DEFAULT_MODE


class TestSessionStateMigration:
    """Тесты миграции SessionState с старыми mode."""

    def test_migrate_old_mode_code(self) -> None:
        """SessionState с mode=code должен мигрировать на bypass."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "code"},
        )
        assert state.config_values.get("mode") == MODE_BYPASS

    def test_migrate_old_mode_ask(self) -> None:
        """SessionState с mode=ask должен мигрировать на standard."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "ask"},
        )
        assert state.config_values.get("mode") == MODE_STANDARD

    def test_migrate_old_mode_architect(self) -> None:
        """SessionState с mode=architect должен мигрировать на plan."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "architect"},
        )
        assert state.config_values.get("mode") == MODE_PLAN

    def test_migrate_old_mode_debug(self) -> None:
        """SessionState с mode=debug должен мигрировать на standard."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "debug"},
        )
        assert state.config_values.get("mode") == MODE_STANDARD

    def test_new_mode_unchanged(self) -> None:
        """SessionState с новым mode должен остаться без изменений."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "bypass"},
        )
        assert state.config_values.get("mode") == MODE_BYPASS

    def test_no_mode_uses_default(self) -> None:
        """SessionState без mode должен использовать default."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        # config_values может быть пустым, migration добавит default
        mode = state.config_values.get("mode", DEFAULT_MODE)
        assert mode == DEFAULT_MODE


class TestDeprecationWarnings:
    """Тесты deprecation warnings."""

    def test_warning_logged_for_old_mode(self, caplog: pytest.LogCaptureFixture) -> None:
        """При миграции старого mode должен быть warning."""
        with caplog.at_level(logging.WARNING):
            SessionState(
                session_id="sess_1",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"mode": "code"},
            )

        assert any("Deprecated mode" in record.message for record in caplog.records)

    def test_no_warning_for_new_mode(self, caplog: pytest.LogCaptureFixture) -> None:
        """Для нового mode warning не должен логироваться."""
        with caplog.at_level(logging.WARNING):
            SessionState(
                session_id="sess_1",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"mode": "standard"},
            )

        assert not any("Deprecated mode" in record.message for record in caplog.records)
