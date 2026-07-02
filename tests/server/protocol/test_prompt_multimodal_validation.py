"""Тесты валидации image, audio и resource в validate_prompt_content."""

from codelab.server.protocol.handlers.prompt import (
    MAX_AUDIO_DATA_SIZE,
    MAX_IMAGE_DATA_SIZE,
    validate_prompt_content,
)


class TestValidateImage:
    """Тесты валидации image content block."""

    def test_valid_image(self) -> None:
        block = {"type": "image", "data": "base64data", "mimeType": "image/png"}
        assert validate_prompt_content("req_1", [block]) is None

    def test_image_missing_data(self) -> None:
        block = {"type": "image", "mimeType": "image/png"}
        error = validate_prompt_content("req_1", [block])
        assert error is not None
        assert "image requires data" in error.error.message

    def test_image_missing_mime_type(self) -> None:
        block = {"type": "image", "data": "base64data"}
        error = validate_prompt_content("req_1", [block])
        assert error is not None
        assert "image requires data" in error.error.message

    def test_image_data_too_large(self) -> None:
        block = {
            "type": "image",
            "data": "x" * (MAX_IMAGE_DATA_SIZE + 1),
            "mimeType": "image/png",
        }
        error = validate_prompt_content("req_1", [block])
        assert error is not None
        assert "image data too large" in error.error.message


class TestValidateAudio:
    """Тесты валидации audio content block."""

    def test_valid_audio(self) -> None:
        block = {"type": "audio", "data": "base64data", "mimeType": "audio/wav"}
        assert validate_prompt_content("req_1", [block]) is None

    def test_audio_missing_data(self) -> None:
        block = {"type": "audio", "mimeType": "audio/wav"}
        error = validate_prompt_content("req_1", [block])
        assert error is not None
        assert "audio requires data" in error.error.message

    def test_audio_missing_mime_type(self) -> None:
        block = {"type": "audio", "data": "base64data"}
        error = validate_prompt_content("req_1", [block])
        assert error is not None
        assert "audio requires data" in error.error.message

    def test_audio_data_too_large(self) -> None:
        block = {
            "type": "audio",
            "data": "x" * (MAX_AUDIO_DATA_SIZE + 1),
            "mimeType": "audio/wav",
        }
        error = validate_prompt_content("req_1", [block])
        assert error is not None
        assert "audio data too large" in error.error.message


class TestValidateResource:
    """Тесты валидации resource content block."""

    def test_valid_resource(self) -> None:
        block = {
            "type": "resource",
            "resource": {"uri": "file:///test", "text": "content"},
        }
        assert validate_prompt_content("req_1", [block]) is None

    def test_resource_missing_uri(self) -> None:
        block = {"type": "resource", "resource": {"text": "content"}}
        error = validate_prompt_content("req_1", [block])
        assert error is not None
        assert "resource requires resource.uri" in error.error.message

    def test_resource_missing_resource_object(self) -> None:
        block = {"type": "resource"}
        error = validate_prompt_content("req_1", [block])
        assert error is not None
        assert "resource requires resource object" in error.error.message
