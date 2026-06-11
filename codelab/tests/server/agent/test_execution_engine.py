"""Тесты для ExecutionEngine."""

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.context_compactor import ContextCompactor
from codelab.server.agent.execution_engine import ExecutionEngine
from codelab.server.llm.models import LLMMessage
from codelab.server.protocol.state import ClientRuntimeCapabilities, SessionState
from codelab.server.tools.base import ToolDefinition


@pytest.fixture
def tool_registry():
    registry = MagicMock()
    registry.get_available_tools.return_value = [
        ToolDefinition(
            name="fs/read_text_file",
            description="Read",
            parameters={},
            kind="filesystem",
        ),
        ToolDefinition(
            name="update_plan",
            description="Plan",
            parameters={},
            kind="plan",
        ),
    ]
    return registry


@pytest.fixture
def session():
    session = MagicMock(spec=SessionState)
    session.session_id = "test_session"
    session.history = [
        {"role": "user", "text": "Hello"},
        {"role": "assistant", "text": "Hi there"},
    ]
    session.runtime_capabilities = ClientRuntimeCapabilities(
        fs_read=True,
        fs_write=False,
        terminal=False,
    )
    session.config_values = {"model": "openai/gpt-4o"}
    return session


@pytest.fixture
def engine(tool_registry):
    return ExecutionEngine(
        tool_registry=tool_registry,
        compactor=ContextCompactor(max_context_tokens=10000, reserved_tokens=1000),
    )


class TestBuildContext:
    """5.5 — поток build context."""

    def test_build_context_returns_agent_context(self, engine, session):
        context = engine.build_context(session, prompt="Test prompt")
        assert context.session_id == "test_session"
        assert context.prompt == [{"type": "text", "text": "Test prompt"}]
        assert len(context.conversation_history) >= 2
        assert len(context.available_tools) >= 1

    def test_build_context_with_system_prompt(self, engine, session):
        context = engine.build_context(
            session, prompt="Test", system_prompt="You are helpful."
        )
        assert context.conversation_history[0].role == "system"
        assert context.conversation_history[0].content == "You are helpful."

    def test_build_context_filters_tools(self, engine, session):
        context = engine.build_context(session, prompt="Test")
        names = {t.name for t in context.available_tools}
        assert "fs/read_text_file" in names
        assert "update_plan" in names  # server-side


class TestEnsureContextFits:
    """5.6 — ensure_context_fits с compaction."""

    @pytest.mark.asyncio
    async def test_short_history_no_compaction(self, engine):
        history = [LLMMessage(role="user", content="short")]
        result, changed, reason = await engine.ensure_context_fits(history)
        assert changed is False
        assert reason == "history_too_short"

    @pytest.mark.asyncio
    async def test_within_limit_no_compaction(self, engine):
        history = [LLMMessage(role="user", content="short") for _ in range(10)]
        result, changed, reason = await engine.ensure_context_fits(history)
        assert changed is False
        assert reason == "within_limit"

    @pytest.mark.asyncio
    async def test_no_compactor_returns_unchanged(self):
        engine = ExecutionEngine(
            tool_registry=MagicMock(),
            compactor=None,
        )
        history = [LLMMessage(role="user", content="test")]
        result, changed, reason = await engine.ensure_context_fits(history)
        assert changed is False
        assert reason == "no_compactor"
        assert result == history
