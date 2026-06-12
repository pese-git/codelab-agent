"""Тесты для модуля mode (ACP Protocol mode constants и утилиты)."""


from codelab.server.protocol.mode import (
    DEFAULT_MODE,
    MODE_BYPASS,
    MODE_PLAN,
    MODE_STANDARD,
    OLD_TO_NEW_MODE,
    VALID_MODES,
    is_mode_auto_execute,
    is_mode_read_only,
    is_tool_blocked_in_plan_mode,
    is_valid_mode,
    normalize_mode,
)


class TestModeConstants:
    def test_valid_modes(self):
        assert {MODE_PLAN, MODE_STANDARD, MODE_BYPASS} == VALID_MODES

    def test_default_mode(self):
        assert DEFAULT_MODE == MODE_STANDARD

    def test_mode_values(self):
        assert MODE_PLAN == "plan"
        assert MODE_STANDARD == "standard"
        assert MODE_BYPASS == "bypass"


class TestIsValidMode:
    def test_valid_modes(self):
        assert is_valid_mode("plan") is True
        assert is_valid_mode("standard") is True
        assert is_valid_mode("bypass") is True

    def test_invalid_modes(self):
        assert is_valid_mode("ask") is False
        assert is_valid_mode("code") is False
        assert is_valid_mode("architect") is False
        assert is_valid_mode("debug") is False
        assert is_valid_mode("unknown") is False
        assert is_valid_mode("") is False


class TestNormalizeMode:
    def test_valid_modes_unchanged(self):
        assert normalize_mode("plan") == "plan"
        assert normalize_mode("standard") == "standard"
        assert normalize_mode("bypass") == "bypass"

    def test_backward_compatibility(self):
        assert normalize_mode("ask") == MODE_STANDARD
        assert normalize_mode("code") == MODE_BYPASS
        assert normalize_mode("architect") == MODE_PLAN
        assert normalize_mode("debug") == MODE_STANDARD

    def test_unknown_falls_back_to_default(self):
        assert normalize_mode("unknown") == DEFAULT_MODE
        assert normalize_mode("") == DEFAULT_MODE

    def test_all_old_modes_mapped(self):
        for old_mode in OLD_TO_NEW_MODE:
            result = normalize_mode(old_mode)
            assert result in VALID_MODES


class TestModePredicates:
    def test_is_mode_read_only(self):
        assert is_mode_read_only(MODE_PLAN) is True
        assert is_mode_read_only(MODE_STANDARD) is False
        assert is_mode_read_only(MODE_BYPASS) is False

    def test_is_mode_auto_execute(self):
        assert is_mode_auto_execute(MODE_BYPASS) is True
        assert is_mode_auto_execute(MODE_STANDARD) is False
        assert is_mode_auto_execute(MODE_PLAN) is False


class TestPlanModeToolBlocking:
    def test_blocked_kinds(self):
        assert is_tool_blocked_in_plan_mode("edit") is True
        assert is_tool_blocked_in_plan_mode("delete") is True
        assert is_tool_blocked_in_plan_mode("execute") is True
        assert is_tool_blocked_in_plan_mode("bash") is True
        assert is_tool_blocked_in_plan_mode("terminal") is True

    def test_allowed_kinds(self):
        assert is_tool_blocked_in_plan_mode("read") is False
        assert is_tool_blocked_in_plan_mode("search") is False
        assert is_tool_blocked_in_plan_mode("think") is False
        assert is_tool_blocked_in_plan_mode("fetch") is False
        assert is_tool_blocked_in_plan_mode("move") is False

    def test_case_insensitive(self):
        assert is_tool_blocked_in_plan_mode("EDIT") is True
        assert is_tool_blocked_in_plan_mode("Read") is False
