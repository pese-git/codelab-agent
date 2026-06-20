"""Тесты для PromptContext с content_parts."""

from codelab.server.llm.content_parts import ContentPart
from codelab.server.protocol.handlers.pipeline.context import PromptContext
from codelab.server.protocol.state import SessionState


def _make_minimal_context(**kwargs: object) -> PromptContext:
    session = SessionState(session_id="test-session", cwd="/tmp")
    defaults = {
        "session_id": "test-session",
        "session": session,
        "request_id": "req_1",
        "params": {},
        "raw_text": "hello",
    }
    defaults.update(kwargs)
    return PromptContext(**defaults)  # type: ignore[arg-type]


class TestPromptContextContentParts:
    """Тесты content_parts в PromptContext."""

    def test_default_empty_content_parts(self) -> None:
        ctx = _make_minimal_context()
        assert ctx.content_parts == []

    def test_content_parts_with_items(self) -> None:
        parts = [
            ContentPart.make_text("Hello"),
            ContentPart.make_image(data="abc", mime_type="image/png"),
        ]
        ctx = _make_minimal_context(content_parts=parts)
        assert len(ctx.content_parts) == 2
        assert ctx.content_parts[0].type == "text"
        assert ctx.content_parts[1].type == "image"
