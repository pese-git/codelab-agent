"""Unit тесты для PromptMapper."""

from codelab.server.domain.conversation import Image, Resource
from codelab.server.domain.prompt import UserPrompt
from codelab.server.mapping.prompt_mapper import PromptMapper


class TestPromptMapperFromAcpBlocks:
    def test_text_only(self) -> None:
        blocks = [{"type": "text", "text": "hello"}]
        prompt = PromptMapper.from_acp_blocks(blocks)
        assert prompt.text == "hello"
        assert prompt.resources == []
        assert prompt.images == []

    def test_multiple_text(self) -> None:
        blocks = [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ]
        prompt = PromptMapper.from_acp_blocks(blocks)
        assert prompt.text == "hello\nworld"

    def test_with_resource(self) -> None:
        blocks = [
            {"type": "text", "text": "check"},
            {"type": "resource", "resource": {"uri": "file:///tmp", "name": "test"}},
        ]
        prompt = PromptMapper.from_acp_blocks(blocks)
        assert prompt.text == "check"
        assert len(prompt.resources) == 1
        assert prompt.resources[0].uri == "file:///tmp"

    def test_with_image(self) -> None:
        blocks = [
            {"type": "image", "data": "base64data", "format": "png"},
        ]
        prompt = PromptMapper.from_acp_blocks(blocks)
        assert len(prompt.images) == 1
        assert prompt.images[0].data == "base64data"

    def test_empty_blocks(self) -> None:
        prompt = PromptMapper.from_acp_blocks([])
        assert prompt.text == ""


class TestPromptMapperToAcpBlocks:
    def test_text_only(self) -> None:
        prompt = UserPrompt(text="hello")
        blocks = PromptMapper.to_acp_blocks(prompt)
        assert blocks == [{"type": "text", "text": "hello"}]

    def test_with_resource(self) -> None:
        prompt = UserPrompt(
            text="check",
            resources=[Resource(uri="file:///tmp", name="test")],
        )
        blocks = PromptMapper.to_acp_blocks(prompt)
        assert len(blocks) == 2
        assert blocks[0] == {"type": "text", "text": "check"}
        assert blocks[1]["type"] == "resource"

    def test_with_image(self) -> None:
        prompt = UserPrompt(images=[Image(data="base64", format="png")])
        blocks = PromptMapper.to_acp_blocks(prompt)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "image"

    def test_empty_prompt(self) -> None:
        prompt = UserPrompt()
        blocks = PromptMapper.to_acp_blocks(prompt)
        assert blocks == []


class TestPromptMapperRoundTrip:
    def test_round_trip(self) -> None:
        original = UserPrompt(
            text="hello world",
            resources=[Resource(uri="file:///tmp", name="test")],
            images=[Image(data="base64", format="png")],
        )
        blocks = PromptMapper.to_acp_blocks(original)
        restored = PromptMapper.from_acp_blocks(blocks)
        assert restored.text == original.text
        assert len(restored.resources) == 1
        assert len(restored.images) == 1
