"""Тесты покрытия для Markdown компонентов."""

from __future__ import annotations

from unittest.mock import patch

from codelab.client.tui.components.markdown import CodeBlock, InlineMarkdown


class TestInlineMarkdownCoverage:
    """Тесты для непокрытых строк InlineMarkdown."""

    def test_update_content(self) -> None:
        """update_content обновляет raw_content и вызывает базовый update."""
        widget = InlineMarkdown("initial")
        assert widget.raw_content == "initial"

        with patch.object(widget, "update") as update_mock:
            widget.update_content("updated")

        assert widget.raw_content == "updated"
        update_mock.assert_called_once_with("updated")


class TestCodeBlockCoverage:
    """Тесты для непокрытых строк CodeBlock."""

    def test_update_code(self) -> None:
        """update_code обновляет исходный код и рендерит новый Syntax."""
        block = CodeBlock("print(1)", language="python")

        with patch.object(block, "update") as update_mock:
            block.update_code("print(2)", language="python")

        assert block.code == "print(2)"
        assert block.language == "python"
        update_mock.assert_called_once()

    def test_update_code_same_language(self) -> None:
        """update_code без language сохраняет текущий язык."""
        block = CodeBlock("code", language="rust")

        with patch.object(block, "update") as update_mock:
            block.update_code("new code")

        assert block.code == "new code"
        assert block.language == "rust"
        update_mock.assert_called_once()
