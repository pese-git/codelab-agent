"""Тесты read-порта SessionView (ADR-005, Фаза 1).

Проверяют, что ядро (`ExecutionEngine` + `HistoryBuilder` + `ToolFilter`)
работает поверх порта `SessionView` без Pydantic `protocol.state.SessionState` —
достаточно простого `FakeSessionView`. Это и есть смысл read-развязки: подать
ядру не-ACP драйвер.
"""

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.core.execution_engine import ExecutionEngine
from codelab.server.agent.core.history_builder import HistoryBuilder
from codelab.server.agent.core.tool_filter import ToolFilter
from codelab.server.llm.content_parts import ContentPart
from codelab.server.tools.base import ToolDefinition
from tests.server.agent.fakes import FakeCapabilities, FakeSessionView


@pytest.fixture
def tool_registry():
    registry = MagicMock()
    registry.get_available_tools.return_value = [
        ToolDefinition(name="fs/read_text_file", description="Read", parameters={}, kind="read"),
        ToolDefinition(name="fs/write_text_file", description="Write", parameters={}, kind="edit"),
        ToolDefinition(name="terminal/create", description="Term", parameters={}, kind="execute"),
        ToolDefinition(name="update_plan", description="Plan", parameters={}, kind="plan"),
    ]
    return registry


@pytest.fixture
def engine(tool_registry):
    return ExecutionEngine(tool_registry=tool_registry)


class TestExecutionEngineOverPort:
    """Ядро принимает произвольную реализацию SessionView (не SessionState)."""

    @pytest.mark.asyncio
    async def test_build_context_without_pydantic_session(self, engine):
        session = FakeSessionView(
            session_id="s1",
            config_values={"model": "openai/gpt-4o", "_agent": ""},
            runtime_capabilities=FakeCapabilities(fs_read=True),
            history=[
                {"role": "user", "text": "Hello"},
                {"role": "assistant", "text": "Hi"},
            ],
        )

        context = await engine.build_context(session, prompt="Do it")

        assert context.session_id == "s1"
        assert context.model == "openai/gpt-4o"
        assert context.prompt == [{"type": "text", "text": "Do it"}]
        assert len(context.conversation_history) >= 2

    @pytest.mark.asyncio
    async def test_capabilities_gate_via_port(self, engine):
        """fs_read=True, fs_write/terminal=False → доступны read + серверные."""
        session = FakeSessionView(runtime_capabilities=FakeCapabilities(fs_read=True))

        context = await engine.build_context(session, prompt="x")

        names = {t.name for t in context.available_tools}
        assert "fs/read_text_file" in names
        assert "update_plan" in names  # серверный, всегда доступен
        assert "fs/write_text_file" not in names
        assert "terminal/create" not in names

    @pytest.mark.asyncio
    async def test_continuation_context_over_port(self, engine):
        session = FakeSessionView(
            history=[
                {"role": "assistant", "text": "", "tool_calls": [
                    {"id": "c1", "name": "fs/read_text_file", "arguments": {"path": "a"}}
                ]},
                {"role": "tool", "tool_call_id": "c1", "content": "file body"},
            ],
        )

        context = await engine.build_continuation_context(session)

        roles = [m.role for m in context.history]
        assert "tool" in roles


class TestHistoryFidelity:
    """Round-trip: tool_calls и мультимодальный контент не теряются (P2-32)."""

    def test_tool_calls_preserved(self):
        """SessionView.history сохраняет tool_calls (доменный ConversationMessage — лоссовый)."""
        history = [
            {
                "role": "assistant",
                "text": "",
                "tool_calls": [{"id": "c1", "name": "grep", "arguments": {"q": "x"}}],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "match"},
        ]

        messages = HistoryBuilder().build(history)

        assistant = next(m for m in messages if m.role == "assistant")
        assert assistant.tool_calls is not None
        assert assistant.tool_calls[0].name == "grep"
        tool_msg = next(m for m in messages if m.role == "tool")
        assert tool_msg.tool_call_id == "c1"

    def test_multimodal_image_prompt_preserved(self):
        """Блок image в истории не схлопывается в текст, а даёт ContentPart."""
        history = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "смотри"},
                    {"type": "image", "data": "BASE64", "mimeType": "image/png"},
                ],
            }
        ]

        messages = HistoryBuilder().build(history)

        content = messages[0].content
        assert isinstance(content, list)
        assert any(isinstance(p, ContentPart) and p.is_multimodal for p in content)


class TestToolFilterAcceptsAnyCapabilities:
    """ToolFilter принимает любой ClientCapabilitiesView (не только протокольный)."""

    def test_terminal_gate(self):
        tools = [
            ToolDefinition(name="terminal/create", description="", parameters={}, kind="execute"),
        ]
        allowed = ToolFilter().filter(tools, FakeCapabilities(terminal=True))
        assert [t.name for t in allowed] == ["terminal/create"]

        denied = ToolFilter().filter(tools, FakeCapabilities(terminal=False))
        assert denied == []
