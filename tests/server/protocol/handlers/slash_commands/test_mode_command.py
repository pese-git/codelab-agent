"""Unit-тесты для /mode slash command handler.

Тестирует:
- Показ текущего режима без аргументов
- Установка нового режима
- Нормализация старых режимов
- Ошибки для неизвестных режимов
"""

from __future__ import annotations

from codelab.server.protocol.handlers.slash_commands.builtin.mode import (
    ModeCommandHandler,
)
from codelab.server.protocol.state import SessionState


def _make_session(mode: str = "standard") -> SessionState:
    """Создать сессию с указанным mode."""
    return SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
        config_values={"mode": mode},
    )


class TestModeCommandShow:
    """Тесты показа текущего режима."""

    def test_show_current_mode(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session(mode="bypass")
        result = handler.execute([], session)

        assert result is not None
        text = result.content[0]["text"]
        assert "bypass" in text
        assert "Текущий режим" in text

    def test_show_available_modes(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session()
        result = handler.execute([], session)

        text = result.content[0]["text"]
        assert "plan" in text
        assert "standard" in text
        assert "bypass" in text

    def test_show_current_mode_marker(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session(mode="plan")
        result = handler.execute([], session)

        text = result.content[0]["text"]
        assert "→ `plan`" in text
        assert " `standard`" in text
        assert " `bypass`" in text

    def test_show_default_mode_when_not_set(self) -> None:
        handler = ModeCommandHandler()
        session = SessionState(session_id="test", cwd="/tmp", mcp_servers=[])
        result = handler.execute([], session)

        text = result.content[0]["text"]
        assert "standard" in text


class TestModeCommandSet:
    """Тесты установки режима."""

    def test_set_mode_plan(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session(mode="standard")
        result = handler.execute(["plan"], session)

        assert result is not None
        assert session.config_values.get("mode") == "plan"
        text = result.content[0]["text"]
        assert "standard" in text
        assert "plan" in text

    def test_set_mode_bypass(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session(mode="standard")
        result = handler.execute(["bypass"], session)

        assert session.config_values.get("mode") == "bypass"
        assert result is not None
        assert result.updates is not None
        assert len(result.updates) == 1
        assert result.updates[0]["mode"] == "bypass"

    def test_set_same_mode_no_change(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session(mode="standard")
        result = handler.execute(["standard"], session)

        text = result.content[0]["text"]
        assert "уже активен" in text
        assert session.config_values.get("mode") == "standard"

    def test_set_mode_case_insensitive(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session()
        handler.execute(["PLAN"], session)

        assert session.config_values.get("mode") == "plan"


class TestModeCommandNormalization:
    """Тесты нормализации старых режимов."""

    def test_old_mode_ask_normalizes(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session(mode="bypass")
        result = handler.execute(["ask"], session)

        assert session.config_values.get("mode") == "standard"
        text = result.content[0]["text"]
        assert "нормализовано" in text
        assert "ask" in text

    def test_old_mode_code_normalizes(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session()
        result = handler.execute(["code"], session)

        assert session.config_values.get("mode") == "bypass"
        assert "нормализовано" in result.content[0]["text"]

    def test_old_mode_architect_normalizes(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session()
        result = handler.execute(["architect"], session)

        assert session.config_values.get("mode") == "plan"
        assert "нормализовано" in result.content[0]["text"]


class TestModeCommandInvalid:
    """Тесты невалидных режимов."""

    def test_unknown_mode_error(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session()
        result = handler.execute(["unknown"], session)

        text = result.content[0]["text"]
        assert "Неизвестный режим" in text
        assert "unknown" in text

    def test_empty_string_mode_error(self) -> None:
        handler = ModeCommandHandler()
        session = _make_session()
        result = handler.execute([""], session)

        text = result.content[0]["text"]
        assert "Неизвестный режим" in text


class TestModeCommandDefinition:
    """Тесты определения команды."""

    def test_get_definition(self) -> None:
        handler = ModeCommandHandler()
        definition = handler.get_definition()

        assert definition.name == "mode"
        assert definition.description is not None
        assert definition.input is not None
