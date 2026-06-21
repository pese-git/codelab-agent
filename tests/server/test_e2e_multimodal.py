"""E2E тесты для мультимодального промпта."""

from codelab.server.llm.models import LLMMessage
from codelab.server.llm.providers.anthropic import AnthropicProvider
from codelab.server.llm.providers.openai import OpenAIProvider
from codelab.server.protocol.content.acp_mapper import ACPContentMapper
from codelab.server.protocol.handlers.auth import initialize


class TestE2EPromptWithImage:
    """E2E: session/prompt с image → LLM получает форматированный image."""

    def test_image_prompt_to_openai(self) -> None:
        blocks = [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image", "data": "base64data", "mimeType": "image/png"},
        ]
        parts = ACPContentMapper().map_blocks(blocks)
        msg = LLMMessage(role="user", content=parts)

        provider = OpenAIProvider()
        formatted = provider._convert_to_openai_format([msg])

        assert len(formatted) == 1
        content = formatted[0]["content"]
        assert isinstance(content, list)
        assert any(c["type"] == "image_url" for c in content)

    def test_image_prompt_to_anthropic(self) -> None:
        blocks = [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image", "data": "base64data", "mimeType": "image/png"},
        ]
        parts = ACPContentMapper().map_blocks(blocks)
        msg = LLMMessage(role="user", content=parts)

        provider = AnthropicProvider()
        formatted = provider._convert_to_anthropic_format([msg])

        assert len(formatted) == 1
        content = formatted[0]["content"]
        assert isinstance(content, list)
        assert any(c["type"] == "image" for c in content)


class TestE2EPromptWithResource:
    """E2E: session/prompt с resource → LLM получает текстовый fallback."""

    def test_resource_prompt_becomes_text(self) -> None:
        blocks = [
            {"type": "resource", "resource": {"uri": "file:///test.py", "text": "print('hi')"}},
        ]
        parts = ACPContentMapper().map_blocks(blocks)

        assert len(parts) == 1
        assert parts[0].type == "text"
        assert "file:///test.py" in parts[0].text
        assert "print('hi')" in parts[0].text


class TestE2EMixedContent:
    """E2E: session/prompt со смешанным содержимым."""

    def test_mixed_content_to_openai(self) -> None:
        blocks = [
            {"type": "text", "text": "Analyze this:"},
            {"type": "image", "data": "abc", "mimeType": "image/jpeg"},
            {"type": "resource_link", "uri": "file:///doc.md", "name": "doc.md"},
        ]
        parts = ACPContentMapper().map_blocks(blocks)
        msg = LLMMessage(role="user", content=parts)

        provider = OpenAIProvider()
        formatted = provider._convert_to_openai_format([msg])

        content = formatted[0]["content"]
        assert isinstance(content, list)
        assert len(content) == 3
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"
        assert content[2]["type"] == "text"


class TestE2EInitializeCapabilities:
    """E2E: ответ initialize включает корректные возможности."""

    def test_initialize_capabilities(self) -> None:
        response = initialize(
            request_id="req_1",
            params={"protocolVersion": 1, "clientCapabilities": {}},
            supported_protocol_versions=(1,),
            require_auth=False,
            auth_methods=[],
        )
        result = response.result
        assert isinstance(result, dict)
        caps = result["agentCapabilities"]["promptCapabilities"]
        assert caps["image"] is True
        assert caps["audio"] is False
        assert caps["embeddedContext"] is True
