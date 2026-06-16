"""Тесты для PlanExtractor - извлечения плана из ответа LLM."""

import pytest

from codelab.server.agent.plan_extractor import (
    ALLOWED_PRIORITIES,
    ALLOWED_STATUSES,
    PlanEntry,
    PlanExtractor,
)


class TestPlanEntry:
    """Тесты для PlanEntry dataclass."""

    def test_plan_entry_to_dict(self) -> None:
        """Проверить преобразование в словарь."""
        entry = PlanEntry(
            content="Test task",
            priority="high",
            status="pending",
        )
        result = entry.to_dict()
        
        assert result == {
            "content": "Test task",
            "priority": "high",
            "status": "pending",
        }


class TestPlanExtractor:
    """Тесты для PlanExtractor."""

    @pytest.fixture
    def extractor(self) -> PlanExtractor:
        """Создать экземпляр extractor."""
        return PlanExtractor()

    def test_extract_from_text_json_block(self, extractor: PlanExtractor) -> None:
        """Извлечение плана из JSON в markdown code block."""
        text = """
Вот мой план:

```json
{
  "plan": [
    {"content": "Step 1", "priority": "high", "status": "pending"},
    {"content": "Step 2", "priority": "medium", "status": "pending"}
  ]
}
```

Начну выполнение.
"""
        result = extractor.extract_from_text(text)
        
        assert result is not None
        assert len(result) == 2
        assert result[0]["content"] == "Step 1"
        assert result[0]["priority"] == "high"
        assert result[1]["content"] == "Step 2"

    def test_extract_from_text_inline_json(self, extractor: PlanExtractor) -> None:
        """Извлечение плана из inline JSON."""
        text = """
План: {"plan": [{"content": "Task 1", "priority": "low", "status": "completed"}]}
"""
        result = extractor.extract_from_text(text)
        
        assert result is not None
        assert len(result) == 1
        assert result[0]["content"] == "Task 1"
        assert result[0]["status"] == "completed"

    def test_extract_from_text_no_plan(self, extractor: PlanExtractor) -> None:
        """Когда план не найден, вернуть None."""
        text = "Обычный текст без плана."
        result = extractor.extract_from_text(text)
        assert result is None

    def test_extract_from_text_empty(self, extractor: PlanExtractor) -> None:
        """Пустой текст возвращает None."""
        assert extractor.extract_from_text("") is None
        assert extractor.extract_from_text(None) is None  # type: ignore[arg-type]

    def test_extract_from_text_invalid_json(self, extractor: PlanExtractor) -> None:
        """Невалидный JSON возвращает None."""
        text = '```json\n{"plan": [broken json]}\n```'
        result = extractor.extract_from_text(text)
        assert result is None

    def test_extract_from_tool_call(self, extractor: PlanExtractor) -> None:
        """Извлечение плана из tool call update_plan."""
        # Формат с объектом с атрибутами
        class ToolCall:
            name = "update_plan"
            arguments = {
                "entries": [
                    {"content": "Task A", "priority": "high", "status": "pending"},
                ]
            }
        
        result = extractor.extract_from_tool_call([ToolCall()])
        
        assert result is not None
        assert len(result) == 1
        assert result[0]["content"] == "Task A"

    def test_extract_from_tool_call_dict(self, extractor: PlanExtractor) -> None:
        """Извлечение плана из tool call в формате словаря."""
        tool_calls = [
            {
                "name": "update_plan",
                "arguments": {
                    "entries": [
                        {"content": "Dict Task", "priority": "low", "status": "completed"},
                    ]
                }
            }
        ]
        
        result = extractor.extract_from_tool_call(tool_calls)
        
        assert result is not None
        assert result[0]["content"] == "Dict Task"

    def test_extract_from_tool_call_json_arguments(self, extractor: PlanExtractor) -> None:
        """Извлечение с arguments как JSON строкой."""
        json_args = (
            '{"entries": [{"content": "JSON args", '
            '"priority": "medium", "status": "pending"}]}'
        )
        tool_calls = [
            {
                "name": "update_plan",
                "arguments": json_args,
            }
        ]
        
        result = extractor.extract_from_tool_call(tool_calls)
        
        assert result is not None
        assert result[0]["content"] == "JSON args"

    def test_extract_from_tool_call_no_update_plan(self, extractor: PlanExtractor) -> None:
        """Когда нет update_plan, вернуть None."""
        tool_calls = [
            {"name": "other_tool", "arguments": {}}
        ]
        result = extractor.extract_from_tool_call(tool_calls)
        assert result is None

    def test_extract_from_tool_call_empty(self, extractor: PlanExtractor) -> None:
        """Пустой список tool_calls возвращает None."""
        assert extractor.extract_from_tool_call([]) is None
        assert extractor.extract_from_tool_call(None) is None  # type: ignore[arg-type]

    def test_validate_entries_normalization(self, extractor: PlanExtractor) -> None:
        """Проверить нормализацию entries."""
        raw = [
            {"content": "  Task with spaces  ", "priority": "high", "status": "pending"},
            {"content": "Normal", "priority": "invalid", "status": "unknown"},
        ]
        
        entries = extractor._validate_entries(raw)
        
        assert len(entries) == 2
        # Пробелы убраны
        assert entries[0].content == "Task with spaces"
        # Невалидные значения заменены на defaults
        assert entries[1].priority == "medium"
        assert entries[1].status == "pending"

    def test_validate_entries_skip_invalid(self, extractor: PlanExtractor) -> None:
        """Пропустить entries без content."""
        raw = [
            {"priority": "high", "status": "pending"},  # Нет content
            {"content": "", "priority": "high", "status": "pending"},  # Пустой content
            {"content": "Valid", "priority": "low", "status": "completed"},
        ]
        
        entries = extractor._validate_entries(raw)
        
        assert len(entries) == 1
        assert entries[0].content == "Valid"

    def test_validate_entries_title_alias(self, extractor: PlanExtractor) -> None:
        """Поле title как альтернатива content."""
        raw = [
            {"title": "Task Title", "priority": "medium", "status": "in_progress"},
        ]
        
        entries = extractor._validate_entries(raw)
        
        assert len(entries) == 1
        assert entries[0].content == "Task Title"


class TestConstants:
    """Тесты для констант."""

    def test_allowed_priorities(self) -> None:
        """Проверить допустимые приоритеты."""
        assert {"low", "medium", "high"} == ALLOWED_PRIORITIES

    def test_allowed_statuses(self) -> None:
        """Проверить допустимые статусы."""
        expected_statuses = {"pending", "in_progress", "completed"}
        assert expected_statuses == ALLOWED_STATUSES
