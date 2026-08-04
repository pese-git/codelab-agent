"""Тесты объявляемых агентом возможностей промпта и capabilities в initialize."""

from codelab.server.protocol.handlers.auth import _PROMPT_CAPABILITIES, initialize
from codelab.shared.prompt_capabilities import PromptCapabilities


class TestAgentPromptCapabilities:
    """Возможности промпта, объявляемые агентом в handshake."""

    def test_uses_shared_type(self) -> None:
        """Тип общий с клиентом: по ACP это `agentCapabilities.promptCapabilities`."""
        assert isinstance(_PROMPT_CAPABILITIES, PromptCapabilities)

    def test_server_profile(self) -> None:
        assert _PROMPT_CAPABILITIES.image is True
        assert _PROMPT_CAPABILITIES.audio is True
        assert _PROMPT_CAPABILITIES.embedded_context is True

    def test_wire_keys_unchanged(self) -> None:
        """Wire-форма — ровно ACP-имена, включая camelCase `embeddedContext`."""
        assert _PROMPT_CAPABILITIES.to_dict() == {
            "image": True,
            "audio": True,
            "embeddedContext": True,
        }


class TestInitializeCapabilities:
    """Тесты capabilities в ответе initialize."""

    def test_initialize_includes_image_true(self) -> None:
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

    def test_initialize_includes_embedded_context_true(self) -> None:
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
        assert caps["embeddedContext"] is True

    def test_initialize_includes_audio_true(self) -> None:
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
        assert caps["audio"] is True
