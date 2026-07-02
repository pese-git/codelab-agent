"""Тесты для AudioContentWidget."""

from codelab.client.tui.components.audio_content import AudioContentWidget


class TestAudioContentWidget:
    """Тесты для AudioContentWidget."""

    def test_create_widget(self) -> None:
        """Проверка создания виджета."""
        widget = AudioContentWidget(
            data="base64data",
            mime_type="audio/wav",
        )
        assert widget.mime_type == "audio/wav"
        assert widget.data_size == 10

    def test_from_content_block(self) -> None:
        """Проверка создания из content block."""
        block = {
            "type": "audio",
            "data": "base64data",
            "mimeType": "audio/mp3",
        }
        widget = AudioContentWidget.from_content_block(block)
        assert widget.mime_type == "audio/mp3"
        assert widget.data_size == 10

    def test_data_size_formatting(self) -> None:
        """Проверка форматирования размера данных."""
        # Маленький размер (B)
        widget = AudioContentWidget(data="x" * 100, mime_type="audio/wav")
        assert widget.data_size == 100

        # Средний размер (KB)
        widget = AudioContentWidget(data="x" * 2048, mime_type="audio/wav")
        assert widget.data_size == 2048

        # Большой размер (MB)
        widget = AudioContentWidget(data="x" * (1024 * 1024), mime_type="audio/wav")
        assert widget.data_size == 1024 * 1024
