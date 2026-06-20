"""Тесты для ImageContentWidget."""

from codelab.client.tui.components.image_content import ImageContentWidget


class TestImageContentWidget:
    """Тесты для ImageContentWidget."""

    def test_create_widget(self) -> None:
        """Проверка создания виджета."""
        widget = ImageContentWidget(
            data="base64data",
            mime_type="image/png",
        )
        assert widget.mime_type == "image/png"
        assert widget.data_size == 10

    def test_create_widget_with_uri(self) -> None:
        """Проверка создания виджета с URI."""
        widget = ImageContentWidget(
            data="base64data",
            mime_type="image/jpeg",
            uri="file:///path/to/image.jpg",
        )
        assert widget.mime_type == "image/jpeg"

    def test_from_content_block(self) -> None:
        """Проверка создания из content block."""
        block = {
            "type": "image",
            "data": "base64data",
            "mimeType": "image/png",
            "uri": "file:///test.png",
        }
        widget = ImageContentWidget.from_content_block(block)
        assert widget.mime_type == "image/png"
        assert widget.data_size == 10

    def test_data_size_formatting(self) -> None:
        """Проверка форматирования размера данных."""
        # Маленький размер (B)
        widget = ImageContentWidget(data="x" * 100, mime_type="image/png")
        assert widget.data_size == 100

        # Средний размер (KB)
        widget = ImageContentWidget(data="x" * 2048, mime_type="image/png")
        assert widget.data_size == 2048

        # Большой размер (MB)
        widget = ImageContentWidget(data="x" * (1024 * 1024), mime_type="image/png")
        assert widget.data_size == 1024 * 1024
