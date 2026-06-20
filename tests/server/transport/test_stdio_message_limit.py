"""Тесты для MAX_STDIO_MESSAGE_SIZE и обработки переполнения буфера."""

from codelab.server.transport.stdio import MAX_STDIO_MESSAGE_SIZE


class TestMaxStdioMessageSize:
    """Тесты константы MAX_STDIO_MESSAGE_SIZE."""

    def test_constant_value(self) -> None:
        """Константа равна 25 MB."""
        assert MAX_STDIO_MESSAGE_SIZE == 25 * 1024 * 1024

    def test_constant_covers_max_image(self) -> None:
        """Константа покрывает максимальный размер image (20 MB base64)."""
        max_image_base64 = 20 * 1024 * 1024
        assert max_image_base64 < MAX_STDIO_MESSAGE_SIZE
