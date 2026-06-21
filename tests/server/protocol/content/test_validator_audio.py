"""Тесты для ContentValidator с audio content."""

from codelab.server.protocol.content.validator import ContentValidator


class TestAudioValidation:
    """Тесты валидации audio content."""

    def test_valid_audio_with_mimetype(self) -> None:
        """Валидный audio с mimeType."""
        validator = ContentValidator()
        valid, err = validator.validate_content_item({
            "type": "audio",
            "data": "base64data",
            "mimeType": "audio/wav",
        })
        assert valid is True
        assert err is None

    def test_valid_audio_mp3(self) -> None:
        """Валидный audio с MP3 форматом."""
        validator = ContentValidator()
        valid, err = validator.validate_content_item({
            "type": "audio",
            "data": "base64data",
            "mimeType": "audio/mp3",
        })
        assert valid is True
        assert err is None

    def test_invalid_audio_missing_mimetype(self) -> None:
        """Невалидный audio без mimeType."""
        validator = ContentValidator()
        valid, err = validator.validate_content_item({
            "type": "audio",
            "data": "base64data",
        })
        assert valid is False
        assert err is not None
        assert "mimeType" in err

    def test_invalid_audio_missing_data(self) -> None:
        """Невалидный audio без data."""
        validator = ContentValidator()
        valid, err = validator.validate_content_item({
            "type": "audio",
            "mimeType": "audio/wav",
        })
        assert valid is False
        assert err is not None
        assert "data" in err

    def test_sanitize_audio_keeps_allowed_fields(self) -> None:
        """Sanitize оставляет разрешённые поля для audio."""
        validator = ContentValidator()
        sanitized = validator.sanitize_content_item({
            "type": "audio",
            "data": "base64data",
            "mimeType": "audio/wav",
            "annotations": {"priority": 1.0},
            "unknown_field": "should_be_removed",
        })
        assert "type" in sanitized
        assert "data" in sanitized
        assert "mimeType" in sanitized
        assert "annotations" in sanitized
        assert "unknown_field" not in sanitized
