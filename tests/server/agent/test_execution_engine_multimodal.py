"""Тесты ExecutionEngine с мультимодальным содержимым."""

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.execution_engine import ExecutionEngine
from codelab.server.llm.content_parts import ContentPart
from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolRegistry


class TestExecutionEngineMultimodal:
    """Тесты build_context с мультимодальным содержимым."""

    def _make_engine(self) -> ExecutionEngine:
        tool_registry = MagicMock(spec=ToolRegistry)
        tool_registry.get_available_tools.return_value = []
        return ExecutionEngine(tool_registry=tool_registry)

    def _make_session(self) -> SessionState:
        return SessionState(session_id="test-session", cwd="/tmp")

    @pytest.mark.asyncio
    async def test_build_context_with_content_parts(self) -> None:
        engine = self._make_engine()
        session = self._make_session()
        parts = [
            ContentPart.make_text("Look:"),
            ContentPart.make_image(data="abc", mime_type="image/png"),
        ]

        ctx = await engine.build_context(session, prompt="", content_parts=parts)

        assert len(ctx.prompt) == 2
        assert ctx.prompt[0]["type"] == "text"
        assert ctx.prompt[0]["text"] == "Look:"
        assert ctx.prompt[1]["type"] == "image"
        assert ctx.prompt[1]["data"] == "abc"

    @pytest.mark.asyncio
    async def test_build_context_without_content_parts_fallback(self) -> None:
        engine = self._make_engine()
        session = self._make_session()

        ctx = await engine.build_context(session, prompt="Hello")

        assert len(ctx.prompt) == 1
        assert ctx.prompt[0]["type"] == "text"
        assert ctx.prompt[0]["text"] == "Hello"
