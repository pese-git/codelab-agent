"""Integration-тесты backward compatibility для mode system.

Тестирует:
- SessionDocument migration с старыми mode значениями
- normalize_mode для всех старых значений
- Deprecation warnings при загрузке старых mode
"""

from __future__ import annotations

import structlog

from codelab.server.domain.mode import (
    DEFAULT_MODE,
    MODE_BYPASS,
    MODE_PLAN,
    MODE_STANDARD,
    OLD_TO_NEW_MODE,
    VALID_MODES,
    normalize_mode,
)
from codelab.server.storage.document import SessionDocument


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
    """Тесты миграции SessionDocument с старыми mode."""

    def test_migrate_old_mode_code(self) -> None:
        """SessionDocument с mode=code должен мигрировать на bypass."""
        state = SessionDocument(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "code"},
        )
        assert state.config_values.get("mode") == MODE_BYPASS

    def test_migrate_old_mode_ask(self) -> None:
        """SessionDocument с mode=ask должен мигрировать на standard."""
        state = SessionDocument(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "ask"},
        )
        assert state.config_values.get("mode") == MODE_STANDARD

    def test_migrate_old_mode_architect(self) -> None:
        """SessionDocument с mode=architect должен мигрировать на plan."""
        state = SessionDocument(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "architect"},
        )
        assert state.config_values.get("mode") == MODE_PLAN

    def test_migrate_old_mode_debug(self) -> None:
        """SessionDocument с mode=debug должен мигрировать на standard."""
        state = SessionDocument(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "debug"},
        )
        assert state.config_values.get("mode") == MODE_STANDARD

    def test_new_mode_unchanged(self) -> None:
        """SessionDocument с новым mode должен остаться без изменений."""
        state = SessionDocument(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"mode": "bypass"},
        )
        assert state.config_values.get("mode") == MODE_BYPASS

    def test_no_mode_uses_default(self) -> None:
        """SessionDocument без mode должен использовать default."""
        state = SessionDocument(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        # config_values может быть пустым, migration добавит default
        mode = state.config_values.get("mode", DEFAULT_MODE)
        assert mode == DEFAULT_MODE


class TestDeprecationWarnings:
    """Тесты deprecation warnings."""

    def test_warning_logged_for_old_mode(self) -> None:
        """При миграции старого mode должен быть warning.

        Событие структурное (`structlog`, конвенция проекта), поэтому и
        проверяется по имени события, а не по тексту сообщения.
        """
        with structlog.testing.capture_logs() as logs:
            SessionDocument(
                session_id="sess_1",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"mode": "code"},
            )

        migrated = [log for log in logs if log["event"] == "session_mode_migrated_from_deprecated"]
        assert len(migrated) == 1
        assert migrated[0]["old_mode"] == "code"
        assert migrated[0]["new_mode"] == "bypass"

    def test_no_warning_for_new_mode(self) -> None:
        """Для нового mode warning не должен логироваться."""
        with structlog.testing.capture_logs() as logs:
            SessionDocument(
                session_id="sess_1",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"mode": "standard"},
            )

        assert not [
            log for log in logs if log["event"] == "session_mode_migrated_from_deprecated"
        ]
