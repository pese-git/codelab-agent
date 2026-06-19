"""Unit тесты для LLMResponseMapper."""

from codelab.server.domain.tool_call import ToolCall
from codelab.server.domain.value_objects import ToolCallStatus
from codelab.server.llm.models import LLMToolCall
from codelab.server.mapping.llm_response_mapper import LLMResponseMapper


class TestLLMResponseMapper:
    def test_empty(self) -> None:
        result = LLMResponseMapper.to_domain([])
        assert result == []

    def test_single_call(self) -> None:
        llm_calls = [LLMToolCall(id="call_1", name="read_file", arguments={"path": "/tmp"})]
        result = LLMResponseMapper.to_domain(llm_calls)
        assert len(result) == 1
        assert isinstance(result[0], ToolCall)
        assert result[0].id == "call_1"
        assert result[0].tool_name == "read_file"
        assert result[0].arguments == {"path": "/tmp"}
        assert result[0].status is ToolCallStatus.PENDING

    def test_multiple_calls(self) -> None:
        llm_calls = [
            LLMToolCall(id="call_1", name="read_file"),
            LLMToolCall(id="call_2", name="write_file"),
        ]
        result = LLMResponseMapper.to_domain(llm_calls)
        assert len(result) == 2
        assert result[0].id == "call_1"
        assert result[1].id == "call_2"
