"""Тесты для Markdown компонентов.

Проверяют:
- InlineMarkdown на базе textual.widgets.Markdown
- MessageContent с Markdown поддержкой
- Устойчивость к литеральным Rich-тегам в тексте LLM
"""

from __future__ import annotations

import pytest

from codelab.client.tui.components.markdown import InlineMarkdown, MarkdownViewer


class TestInlineMarkdown:
    """Тесты для InlineMarkdown компонента."""

    def test_empty_content(self) -> None:
        """Пустой контент не вызывает ошибок."""
        widget = InlineMarkdown("")
        assert widget.raw_content == ""

    def test_plain_text(self) -> None:
        """Обычный текст сохраняется."""
        widget = InlineMarkdown("Hello world")
        assert widget.raw_content == "Hello world"

    def test_bold_text(self) -> None:
        """Bold Markdown синтаксис сохраняется для парсинга."""
        widget = InlineMarkdown("**bold text**")
        assert widget.raw_content == "**bold text**"

    def test_italic_text(self) -> None:
        """Italic Markdown синтаксис сохраняется для парсинга."""
        widget = InlineMarkdown("*italic text*")
        assert widget.raw_content == "*italic text*"

    def test_inline_code(self) -> None:
        """Inline code Markdown синтаксис сохраняется."""
        widget = InlineMarkdown("`code`")
        assert widget.raw_content == "`code`"

    def test_strikethrough(self) -> None:
        """Strikethrough Markdown синтаксис сохраняется."""
        widget = InlineMarkdown("~~deleted~~")
        assert widget.raw_content == "~~deleted~~"

    def test_header(self) -> None:
        """Header Markdown синтаксис сохраняется."""
        widget = InlineMarkdown("# Header")
        assert widget.raw_content == "# Header"

    def test_link(self) -> None:
        """Link Markdown синтаксис сохраняется."""
        widget = InlineMarkdown("[link](https://example.com)")
        assert widget.raw_content == "[link](https://example.com)"

    def test_literal_rich_tags_preserved(self) -> None:
        """Литеральные Rich-теги в тексте сохраняются как есть.
        
        Это ключевой тест — раньше [/bold] в тексте LLM ломал Rich парсер.
        Теперь textual.widgets.Markdown парсит Markdown, а не Rich markup,
        поэтому литеральные скобки не вызывают MarkupError.
        """
        widget = InlineMarkdown("text with [/bold] tag")
        assert widget.raw_content == "text with [/bold] tag"

    def test_mixed_formatting(self) -> None:
        """Комбинированное форматирование сохраняется."""
        widget = InlineMarkdown("**bold** and *italic* with `code`")
        assert "**bold**" in widget.raw_content
        assert "*italic*" in widget.raw_content
        assert "`code`" in widget.raw_content

    def test_brackets_with_formatting(self) -> None:
        """Скобки внутри форматированного текста сохраняются."""
        widget = InlineMarkdown("**array[0]**")
        assert widget.raw_content == "**array[0]**"


class TestMarkdownViewer:
    """Тесты для MarkdownViewer компонента."""

    def test_empty_content(self) -> None:
        """Пустой контент не вызывает ошибок."""
        MarkdownViewer("")

    def test_markdown_content(self) -> None:
        """Markdown контент принимается."""
        MarkdownViewer("# Hello\n**Bold** text")

    def test_literal_rich_tags(self) -> None:
        """Литеральные Rich-теги не ломают парсер."""
        MarkdownViewer("text with [/bold] and [italic] tags")


class TestMarkupErrorResistance:
    """Тесты устойчивости к MarkupError.
    
    Проверяют, что литеральные Rich-теги в тексте LLM
    не вызывают MarkupError при рендеринге.
    """

    @pytest.mark.parametrize("dangerous_text", [
        "text with [/bold] tag",
        "text with [bold] tag",
        "[/italic] orphan close tag",
        "[bold]unclosed tag",
        "array[0] with [1] indices",
        "**bold [/bold] text**",
        "code `[/bold]` in backticks",
    ])
    def test_dangerous_text_does_not_crash(self, dangerous_text: str) -> None:
        """Опасный текст не вызывает ошибок при создании виджета."""
        # Если виджет создаётся без исключений — тест пройден
        widget = InlineMarkdown(dangerous_text)
        assert widget.raw_content == dangerous_text
