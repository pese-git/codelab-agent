"""Тесты чистого разбора tool call в FileChange."""

from __future__ import annotations

from dataclasses import dataclass

from codelab.client.tui.controllers.tool_call_parser import (
    FILE_CHANGE_TOOLS,
    FileChange,
    parse_tool_call_file_change,
)


@dataclass
class _ObjToolCall:
    toolCallId: str
    parameters: dict


class TestParseToolCallFileChange:
    def test_not_found_returns_none(self) -> None:
        assert parse_tool_call_file_change([{"toolCallId": "a"}], "missing") is None

    def test_empty_list_returns_none(self) -> None:
        assert parse_tool_call_file_change([], "x") is None

    def test_dict_with_parameters(self) -> None:
        tc = {
            "toolCallId": "t1",
            "parameters": {"path": "a.py", "old_content": "old", "content": "new"},
        }
        result = parse_tool_call_file_change([tc], "t1")
        assert result == FileChange(file_path="a.py", old_content="old", new_content="new")

    def test_dict_fallback_id_and_rawinput_and_camelcase(self) -> None:
        tc = {
            "id": "t2",
            "rawInput": {"filePath": "b.py", "oldContent": "o", "newContent": "n"},
        }
        result = parse_tool_call_file_change([tc], "t2")
        assert result == FileChange(file_path="b.py", old_content="o", new_content="n")

    def test_object_tool_call(self) -> None:
        tc = _ObjToolCall(toolCallId="t3", parameters={"file_path": "c.py", "content": "x"})
        result = parse_tool_call_file_change([tc], "t3")
        assert result is not None
        assert result.file_path == "c.py"
        assert result.new_content == "x"
        assert result.old_content == ""

    def test_missing_path_defaults_unknown(self) -> None:
        result = parse_tool_call_file_change([{"toolCallId": "t4", "parameters": {}}], "t4")
        assert result is not None
        assert result.file_path == "unknown"

    def test_file_change_tools_constant(self) -> None:
        assert "write_file" in FILE_CHANGE_TOOLS
        assert "read_file" not in FILE_CHANGE_TOOLS
