"""Тесты ValidationStage с мультимодальным содержимым."""

from unittest.mock import MagicMock

import pytest

from codelab.server.llm.content_parts import ContentPart
from codelab.server.protocol.handlers.pipeline.context import PromptContext
from codelab.server.protocol.handlers.pipeline.stages.validation import ValidationStage
from codelab.server.protocol.state import SessionState


def _make_context(
    raw_text: str = "",
    content_parts: list[ContentPart] | None = None,
) -> PromptContext:
    session = SessionState(session_id="test-session", cwd="/tmp")
    return PromptContext(
        session_id="test-session",
        session=session,
        request_id="req_1",
        params={},
        raw_text=raw_text,
        content_parts=content_parts or [],
    )


class TestValidationStageMultimodal:
    """Тесты ValidationStage с multimodal содержимым."""

    def setup_method(self) -> None:
        self.state_manager = MagicMock()
        self.stage = ValidationStage(self.state_manager)

    @pytest.mark.asyncio
    async def test_image_only_passes(self) -> None:
        ctx = _make_context(
            raw_text="",
            content_parts=[ContentPart.make_image(data="abc", mime_type="image/png")],
        )
        result = await self.stage.process(ctx)
        assert result.error_response is None

    @pytest.mark.asyncio
    async def test_text_only_passes(self) -> None:
        ctx = _make_context(
            raw_text="Hello",
            content_parts=[ContentPart.make_text("Hello")],
        )
        result = await self.stage.process(ctx)
        assert result.error_response is None

    @pytest.mark.asyncio
    async def test_empty_prompt_rejected(self) -> None:
        ctx = _make_context(raw_text="", content_parts=[])
        result = await self.stage.process(ctx)
        assert result.error_response is not None
        assert "Empty prompt" in result.error_response.error.message
