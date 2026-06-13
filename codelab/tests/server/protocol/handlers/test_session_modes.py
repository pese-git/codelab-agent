"""Unit-тесты для build_modes_state.

Тестирует:
- Структура availableModes
- currentModeId
- Режим по умолчанию
"""

from __future__ import annotations

from codelab.server.protocol.handlers.session import build_modes_state
from codelab.server.protocol.mode import DEFAULT_MODE, MODE_DESCRIPTIONS, VALID_MODES


def _make_config_specs() -> dict[str, dict[str, str]]:
    """Создать минимальные config_specs."""
    return {
        "mode": {
            "id": "mode",
            "name": "Mode",
            "category": "mode",
            "default": DEFAULT_MODE,
        },
        "model": {
            "id": "model",
            "name": "Model",
            "category": "model",
            "default": "openai/gpt-4o",
        },
    }


class TestBuildModesState:
    """Тесты build_modes_state."""

    def test_available_modes_count(self) -> None:
        result = build_modes_state({}, _make_config_specs())
        assert len(result["availableModes"]) == len(VALID_MODES)

    def test_available_modes_structure(self) -> None:
        result = build_modes_state({}, _make_config_specs())
        for mode in result["availableModes"]:
            assert "id" in mode
            assert "name" in mode
            assert "description" in mode

    def test_available_modes_contains_all(self) -> None:
        result = build_modes_state({}, _make_config_specs())
        mode_ids = {m["id"] for m in result["availableModes"]}
        assert "plan" in mode_ids
        assert "standard" in mode_ids
        assert "bypass" in mode_ids

    def test_available_modes_names_from_descriptions(self) -> None:
        result = build_modes_state({}, _make_config_specs())
        for mode in result["availableModes"]:
            expected_name = MODE_DESCRIPTIONS[mode["id"]]["name"]
            assert mode["name"] == expected_name

    def test_available_modes_sorted(self) -> None:
        result = build_modes_state({}, _make_config_specs())
        mode_ids = [m["id"] for m in result["availableModes"]]
        assert mode_ids == sorted(VALID_MODES)

    def test_current_mode_id_from_values(self) -> None:
        result = build_modes_state({"mode": "bypass"}, _make_config_specs())
        assert result["currentModeId"] == "bypass"

    def test_current_mode_id_default(self) -> None:
        result = build_modes_state({}, _make_config_specs())
        assert result["currentModeId"] == DEFAULT_MODE

    def test_current_mode_id_standard(self) -> None:
        result = build_modes_state({"mode": "standard"}, _make_config_specs())
        assert result["currentModeId"] == "standard"

    def test_current_mode_id_plan(self) -> None:
        result = build_modes_state({"mode": "plan"}, _make_config_specs())
        assert result["currentModeId"] == "plan"

    def test_result_has_both_keys(self) -> None:
        result = build_modes_state({}, _make_config_specs())
        assert "availableModes" in result
        assert "currentModeId" in result
