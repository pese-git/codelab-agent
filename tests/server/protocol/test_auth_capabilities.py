"""Тесты для PromptCapabilityProfile и capabilities в initialize."""

from codelab.server.protocol.handlers.auth import (
    _PROMPT_CAPABILITIES,
    PromptCapabilityProfile,
    initialize,
)


class TestPromptCapabilityProfile:
    """Тесты PromptCapabilityProfile."""

    def test_default_values(self) -> None:
        profile = PromptCapabilityProfile()
        assert profile.image is False
        assert profile.audio is False
        assert profile.embedded_context is False

    def test_server_profile(self) -> None:
        assert _PROMPT_CAPABILITIES.image is True
        assert _PROMPT_CAPABILITIES.audio is True
        assert _PROMPT_CAPABILITIES.embedded_context is True


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
