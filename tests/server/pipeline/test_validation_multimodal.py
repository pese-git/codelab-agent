"""Тесты ValidationStage с мультимодальным содержимым."""

import pytest

from codelab.server.llm.content_parts import ContentPart
from codelab.server.protocol.handlers.pipeline.context import PromptContext
from codelab.server.protocol.handlers.pipeline.stages.validation import ValidationStage
from tests.server._domain_sessions import make_commands, make_domain_session


def _make_context(
    raw_text: str = "",
    content_parts: list[ContentPart] | None = None,
) -> PromptContext:
    session = make_domain_session(session_id="test-session", cwd="/tmp")
    return PromptContext(
        session_id="test-session",
        session=session,
        commands=make_commands(session),
        request_id="req_1",
        params={},
        raw_text=raw_text,
        content_parts=content_parts or [],
    )


class TestValidationStageMultimodal:
    """Тесты ValidationStage с multimodal содержимым."""

    def setup_method(self) -> None:
        self.stage = ValidationStage()

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
