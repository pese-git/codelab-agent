"""Тесты для покрытия непокрытых участков PlanBuilder.

Дополняет существующие тесты проверкой:
- normalize_plan_entries
- build_plan_updates при отсутствии валидных entries
- вспомогательных функций _validate_entry_structure, _normalize_entry_fields,
  _get_allowed_plan_keys
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codelab.server.protocol.handlers.plan_builder import (
    PlanBuilder,
    _get_allowed_plan_keys,
    _normalize_entry_fields,
    _validate_entry_structure,
)
from codelab.server.protocol.state import PromptDirectives, SessionState


@pytest.fixture
def plan_builder() -> PlanBuilder:
    """Создает экземпляр PlanBuilder для тестов."""
    return PlanBuilder()


@pytest.fixture
def session() -> SessionState:
    """Создает экземпляр SessionState для тестов."""
    return SessionState(
        session_id="sess_1",
        cwd="/tmp",
        mcp_servers=[],
    )


@pytest.fixture
def directives() -> PromptDirectives:
    """Создает экземпляр PromptDirectives для тестов."""
    return PromptDirectives()


class TestPlanBuilderNormalizePlanEntries:
    """Тесты для normalize_plan_entries."""

    def test_normalize_plan_entries_delegates(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Делегирует вызов validate_plan_entries."""
        entries = [{"content": "Task"}]
        expected = MagicMock()

        with patch.object(
            plan_builder,
            "validate_plan_entries",
            return_value=expected,
        ) as mock_validate:
            result = plan_builder.normalize_plan_entries(entries)

        mock_validate.assert_called_once_with(entries)
        assert result is expected

    def test_normalize_plan_entries_returns_none_for_invalid(
        self,
        plan_builder: PlanBuilder,
    ) -> None:
        """Возвращает None для невалидных entries."""
        assert plan_builder.normalize_plan_entries([]) is None


class TestPlanBuilderBuildPlanUpdatesEdgeCases:
    """Тесты для граничных случаев build_plan_updates."""

    def test_build_updates_no_valid_entries_logs_and_returns_empty(
        self,
        plan_builder: PlanBuilder,
        session: SessionState,
        directives: PromptDirectives,
    ) -> None:
        """Возвращает пустой список если entries не прошли валидацию."""
        directives.publish_plan = True
        directives.plan_entries = [{}]

        with patch(
            "codelab.server.protocol.handlers.plan_builder.logger"
        ) as mock_logger:
            updates = plan_builder.build_plan_updates(session, "sess_1", directives)

        assert updates == []
        mock_logger.debug.assert_any_call("plan updates: no valid plan entries")

    def test_build_updates_with_non_dict_entry_returns_empty(
        self,
        plan_builder: PlanBuilder,
        session: SessionState,
        directives: PromptDirectives,
    ) -> None:
        """Возвращает пустой список если ни один entry не валиден."""
        directives.publish_plan = True
        directives.plan_entries = ["invalid entry"]

        updates = plan_builder.build_plan_updates(session, "sess_1", directives)

        assert updates == []


class TestValidateEntryStructure:
    """Тесты для _validate_entry_structure."""

    def test_non_dict_returns_false(self) -> None:
        """Отклоняет non-dict значения."""
        assert _validate_entry_structure("string") is False
        assert _validate_entry_structure(["list"]) is False
        assert _validate_entry_structure(123) is False

    def test_dict_without_title_or_content_returns_false(self) -> None:
        """Отклоняет dict без content/title."""
        assert _validate_entry_structure({"priority": "high"}) is False

    def test_non_string_content_returns_false(self) -> None:
        """Отклоняет content не строкового типа."""
        assert _validate_entry_structure({"content": 123}) is False

    def test_non_string_title_returns_false(self) -> None:
        """Отклоняет title не строкового типа."""
        assert _validate_entry_structure({"title": 123}) is False

    def test_valid_content_returns_true(self) -> None:
        """Принимает валидный content."""
        assert _validate_entry_structure({"content": "Task"}) is True

    def test_valid_title_returns_true(self) -> None:
        """Принимает валидный title."""
        assert _validate_entry_structure({"title": "Task"}) is True

    def test_valid_entry_with_both_fields_returns_true(self) -> None:
        """Принимает entry одновременно с content и title."""
        assert _validate_entry_structure({"content": "Task", "title": "Task"}) is True


class TestNormalizeEntryFields:
    """Тесты для _normalize_entry_fields."""

    def test_normalizes_full_entry(self) -> None:
        """Нормализует entry со всеми полями."""
        entry = {
            "content": "  Task  ",
            "description": "  Description  ",
            "priority": "high",
            "status": "in_progress",
        }

        result = _normalize_entry_fields(entry)

        assert result["content"] == "Task"
        assert result["description"] == "Description"
        assert result["priority"] == "high"
        assert result["status"] == "in_progress"

    def test_truncates_long_content(self) -> None:
        """Обрезает слишком длинный content."""
        entry = {"content": "x" * 300}

        result = _normalize_entry_fields(entry)

        assert len(result["content"]) == 200

    def test_truncates_long_description(self) -> None:
        """Обрезает слишком длинный description."""
        entry = {"description": "x" * 600}

        result = _normalize_entry_fields(entry)

        assert len(result["description"]) == 500

    def test_invalid_priority_defaults_to_medium(self) -> None:
        """Устанавливает medium при невалидном priority."""
        result = _normalize_entry_fields({"priority": "invalid"})

        assert result["priority"] == "medium"

    def test_invalid_status_defaults_to_pending(self) -> None:
        """Устанавливает pending при невалидном status."""
        result = _normalize_entry_fields({"status": "invalid"})

        assert result["status"] == "pending"

    def test_cancelled_status_preserved(self) -> None:
        """Сохраняет статус cancelled."""
        result = _normalize_entry_fields({"status": "cancelled"})

        assert result["status"] == "cancelled"

    def test_uses_title_when_content_missing(self) -> None:
        """Использует title если content отсутствует."""
        result = _normalize_entry_fields({"title": "Title task"})

        assert result["content"] == "Title task"

    def test_uses_defaults_for_missing_fields(self) -> None:
        """Использует значения по умолчанию для отсутствующих полей."""
        result = _normalize_entry_fields({})

        assert result["content"] == ""
        assert result["description"] == ""
        assert result["priority"] == "medium"
        assert result["status"] == "pending"

    def test_skips_non_string_content(self) -> None:
        """Сохраняет non-string content как есть после приведения."""
        entry = {"content": 123}

        result = _normalize_entry_fields(entry)

        assert result["content"] == 123


class TestGetAllowedPlanKeys:
    """Тесты для _get_allowed_plan_keys."""

    def test_returns_expected_keys(self) -> None:
        """Возвращает ожидаемое множество разрешенных ключей."""
        keys = _get_allowed_plan_keys()

        assert keys == {
            "content",
            "title",
            "description",
            "priority",
            "status",
        }
