"""Unit тесты для domain ToolCall и ToolResult."""

import pytest

from codelab.server.domain.tool_call import ToolCall, ToolResult, answer_tool_call_id
from codelab.server.domain.value_objects import FileLocation, ToolCallStatus


class TestToolResult:
    def test_defaults(self) -> None:
        result = ToolResult()
        assert result.locations == []
        assert result.raw_output == {}

    def test_with_data(self) -> None:
        loc = FileLocation(path="/tmp/test.py", line=10)
        result = ToolResult(
            locations=[loc],
            raw_output={"content": "hello"},
        )
        assert result.locations == [loc]
        assert result.raw_output == {"content": "hello"}

    def test_frozen(self) -> None:
        result = ToolResult()
        with pytest.raises(AttributeError):
            result.locations = []  # type: ignore[misc]


class TestToolCall:
    def test_defaults(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file")
        assert tc.id == "call_1"
        assert tc.tool_name == "read_file"
        assert tc.arguments == {}
        assert tc.status is ToolCallStatus.PENDING
        assert tc.result is None
        assert tc.locations == []
        assert tc.raw_output == {}

    def test_is_terminal_pending(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file", status=ToolCallStatus.PENDING)
        assert tc.is_terminal is False

    def test_is_terminal_in_progress(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file", status=ToolCallStatus.IN_PROGRESS)
        assert tc.is_terminal is False

    def test_is_terminal_cancelled(self) -> None:
        """CANCELLED терминален — как и в матрице переходов ToolCallHandler."""
        tc = ToolCall(id="call_1", tool_name="read_file", status=ToolCallStatus.CANCELLED)
        assert tc.is_terminal is True

    def test_is_terminal_completed(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file", status=ToolCallStatus.COMPLETED)
        assert tc.is_terminal is True

    def test_is_terminal_failed(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file", status=ToolCallStatus.FAILED)
        assert tc.is_terminal is True

    def test_with_result(self) -> None:
        result = ToolResult(raw_output={"exit_code": 0})
        tc = ToolCall(
            id="call_1",
            tool_name="terminal",
            status=ToolCallStatus.COMPLETED,
            result=result,
        )
        assert tc.result is result
        assert tc.result.raw_output == {"exit_code": 0}

    def test_with_locations(self) -> None:
        loc = FileLocation(path="/tmp/test.py", line=42)
        tc = ToolCall(id="call_1", tool_name="read_file", locations=[loc])
        assert tc.locations == [loc]

    def test_mutable_status(self) -> None:
        """ToolCall — entity с жизненным циклом, статус меняется на месте.

        Мутабельность намеренна (фаза B ADR-006): пересборка на каждую смену
        статуса теряла поля, не перечисленные в конструкторе копии.
        """
        tc = ToolCall(id="call_1", tool_name="read_file", kind="read", title="Read")
        tc.status = ToolCallStatus.IN_PROGRESS
        assert tc.status is ToolCallStatus.IN_PROGRESS
        assert (tc.kind, tc.title) == ("read", "Read")

    def test_equality(self) -> None:
        a = ToolCall(id="call_1", tool_name="read_file")
        b = ToolCall(id="call_1", tool_name="read_file")
        assert a == b


class TestAnswerToolCallId:
    """Правило перевода «внутренняя идентичность → идентичность для модели».

    Шаг 1 ADR-008: до него правило было продублировано десятью выражениями
    `tool_call_id_from_llm or tool_call_id` в четырёх модулях.
    """

    def test_prefers_llm_id(self) -> None:
        assert answer_tool_call_id("chatcmpl-tool-abc", "call_001") == "chatcmpl-tool-abc"

    def test_falls_back_to_internal_id_when_llm_id_absent(self) -> None:
        """Путь без LLM (client-RPC, отмена, служебный вызов) — рабочая ветка.

        Ответ обязан быть отправлен и здесь: без него вызов остаётся без
        `role: tool` и следующий запрос нарушает контракт LLM-API (P2-38).
        """
        assert answer_tool_call_id(None, "call_001") == "call_001"

    def test_falls_back_on_empty_llm_id(self) -> None:
        """Пустая строка — не идентификатор: под ней ответ модель не сопоставит."""
        assert answer_tool_call_id("", "call_001") == "call_001"

    def test_property_delegates_to_rule(self) -> None:
        """Две точки входа, одно правило: объект и пара идентификаторов совпадают."""
        tc = ToolCall(
            id="call_001", tool_name="terminal/create", tool_call_id_from_llm="chatcmpl-tool-abc"
        )
        assert tc.answer_id == answer_tool_call_id(tc.tool_call_id_from_llm, tc.id)
        assert tc.answer_id == "chatcmpl-tool-abc"

    def test_property_without_llm_id(self) -> None:
        tc = ToolCall(id="call_001", tool_name="fs/read_text_file")
        assert tc.answer_id == "call_001"
