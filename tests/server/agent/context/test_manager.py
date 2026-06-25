"""Интеграционные тесты для ContextManager."""

import pytest

from codelab.server.agent.context.manager import DefaultContextManager
from codelab.server.agent.context.models import ContextConfig
from codelab.server.llm.models import CompletionResponse, StopReason


class MockToolRegistry:
    """Mock ToolRegistry для тестирования."""

    def __init__(self):
        self.tools = []

    def get_available_tools(self, session_id: str):
        return self.tools

    async def execute_tool(self, session_id: str, tool_name: str, arguments: dict):
        class Result:
            def __init__(self, success, result):
                self.success = success
                self.result = result

        if tool_name == "fs_search":
            return Result(True, [{"path": "src/main.py"}, {"path": "src/utils.py"}])
        elif tool_name == "fs_read":
            path = arguments.get("path", "")
            return Result(True, {"content": f"# Content of {path}\ndef example():\n    pass\n"})
        return Result(False, None)


class MockLLMForManager:
    """Mock LLM провайдер для тестирования ContextManager."""

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    async def create_completion(self, request):
        return CompletionResponse(
            text=self._response_text,
            tool_calls=[],
            stop_reason=StopReason.END_TURN,
            model=request.model,
        )


@pytest.mark.asyncio
async def test_context_manager_build_context_basic():
    """Тест базовой сборки контекста."""
    tool_registry = MockToolRegistry()
    response = """{
        "task_type": "feature",
        "search_terms": ["authentication"],
        "target_modules": ["src/auth.py"],
        "investigation_depth": 1,
        "needs_tests": false
    }"""
    llm = MockLLMForManager(response)
    config = ContextConfig(enabled=True, gather_enabled=True)

    manager = DefaultContextManager(
        tool_registry=tool_registry,
        config=config,
        llm=llm,
    )

    session = type("Session", (), {"session_id": "test-session"})()
    prompt = [{"type": "text", "text": "Add authentication feature"}]

    envelope = await manager.build_context(
        session=session,
        prompt=prompt,
        agent_scope="single",
        system_prompt="You are a helpful assistant.",
    )

    assert envelope is not None
    assert len(envelope.baseline) > 0
    assert len(envelope.tail) > 0
    assert envelope.baseline_fingerprint != ""
    assert envelope.token_count > 0


@pytest.mark.asyncio
async def test_context_manager_build_context_without_gather():
    """Тест сборки контекста без сбора файлов."""
    tool_registry = MockToolRegistry()
    config = ContextConfig(enabled=True, gather_enabled=False)

    manager = DefaultContextManager(
        tool_registry=tool_registry,
        config=config,
        llm=None,
    )

    session = type("Session", (), {"session_id": "test-session"})()
    prompt = [{"type": "text", "text": "Simple question"}]

    envelope = await manager.build_context(
        session=session,
        prompt=prompt,
        agent_scope="single",
        system_prompt="You are helpful.",
    )

    assert envelope is not None
    assert len(envelope.baseline) == 1
    assert envelope.baseline[0].role == "system"
    assert len(envelope.tail) == 1
    assert envelope.tail[0].role == "user"


@pytest.mark.asyncio
async def test_context_manager_ensure_context_fits_no_truncation():
    """Тест что ensure_context_fits не обрезает если всё помещается."""
    tool_registry = MockToolRegistry()
    config = ContextConfig(enabled=True)

    manager = DefaultContextManager(
        tool_registry=tool_registry,
        config=config,
    )

    from codelab.server.agent.context.models import PayloadEnvelope
    from codelab.server.llm.models import LLMMessage

    envelope = PayloadEnvelope(
        baseline=[LLMMessage(role="system", content="Short system prompt")],
        tail=[LLMMessage(role="user", content="Short question")],
        baseline_fingerprint="test",
        token_count=10,
    )

    result = await manager.ensure_context_fits(
        envelope,
        max_context_tokens=100000,
        reserved_tokens=4096,
    )

    assert result is envelope


@pytest.mark.asyncio
async def test_context_manager_process_subagent_response():
    """Тест обработки ответа субагента."""
    tool_registry = MockToolRegistry()
    config = ContextConfig(enabled=True)

    manager = DefaultContextManager(
        tool_registry=tool_registry,
        config=config,
    )

    result = await manager.process_subagent_response(
        parent_scope="parent",
        subagent_scope="child",
        response=None,
    )

    assert result is not None
    assert result.source_scope == "child"
    assert "child" in result.summary
