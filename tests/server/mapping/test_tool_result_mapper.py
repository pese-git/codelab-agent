"""Unit тесты для ToolResultMapper.

Проверяет:
- Конвертацию ToolExecutionResult в ACP ToolCallContent
- Приоритет поля content над output
- Fallback на text из output если content не задан
"""

from __future__ import annotations

from codelab.server.mapping.tool_result_mapper import ToolResultMapper
from codelab.server.tools.base import ToolExecutionResult


class TestToolResultMapperToAcpContent:
    """Тесты метода to_acp_content()."""

    def test_to_acp_content_returns_result_content_if_set(self) -> None:
        """to_acp_content() возвращает result.content если задан."""
        custom_content = [
            {"type": "terminal", "terminalId": "term_xyz789"},
            {
                "type": "content",
                "content": {"type": "text", "text": "Terminal created"},
            },
        ]
        result = ToolExecutionResult(
            success=True,
            output="Терминал создан",
            content=custom_content,
        )

        acp_content = ToolResultMapper.to_acp_content(result)

        assert acp_content == custom_content

    def test_to_acp_content_fallback_to_output_if_content_not_set(self) -> None:
        """to_acp_content() fallback на text из output если content не задан."""
        result = ToolExecutionResult(
            success=True,
            output="Результат выполнения",
        )

        acp_content = ToolResultMapper.to_acp_content(result)

        assert acp_content == [{"type": "text", "text": "Результат выполнения"}]

    def test_to_acp_content_empty_if_no_output_and_no_content(self) -> None:
        """to_acp_content() возвращает пустой список если нет output и content."""
        result = ToolExecutionResult(success=True)

        acp_content = ToolResultMapper.to_acp_content(result)

        assert acp_content == []

    def test_to_acp_content_empty_list_content_returns_empty(self) -> None:
        """to_acp_content() возвращает пустой список если content — пустой список."""
        result = ToolExecutionResult(
            success=True,
            output="Результат",
            content=[],
        )

        acp_content = ToolResultMapper.to_acp_content(result)

        assert acp_content == []

    def test_to_acp_content_terminal_content_format(self) -> None:
        """to_acp_content() корректно возвращает terminal content."""
        terminal_content = [
            {"type": "terminal", "terminalId": "term_abc123"},
        ]
        result = ToolExecutionResult(
            success=True,
            output="Терминал создан",
            content=terminal_content,
        )

        acp_content = ToolResultMapper.to_acp_content(result)

        assert len(acp_content) == 1
        assert acp_content[0]["type"] == "terminal"
        assert acp_content[0]["terminalId"] == "term_abc123"

    def test_to_acp_content_preserves_order(self) -> None:
        """to_acp_content() сохраняет порядок content items."""
        custom_content = [
            {"type": "terminal", "terminalId": "term_1"},
            {"type": "content", "content": {"type": "text", "text": "First"}},
            {"type": "content", "content": {"type": "text", "text": "Second"}},
        ]
        result = ToolExecutionResult(
            success=True,
            output="Ignored",
            content=custom_content,
        )

        acp_content = ToolResultMapper.to_acp_content(result)

        assert acp_content == custom_content
        assert acp_content[0]["type"] == "terminal"
        assert acp_content[1]["content"]["text"] == "First"
        assert acp_content[2]["content"]["text"] == "Second"
