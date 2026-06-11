"""Компонент для рендеринга Markdown контента в TUI.

Отвечает за:
- Рендеринг Markdown текста с поддержкой Rich разметки
- Syntax highlighting для блоков кода
- Поддержка: заголовки, списки, код, ссылки, жирный/курсив

Референс OpenCode: packages/web/src/ui/markdown.tsx
"""

from __future__ import annotations

from textual.widgets import Markdown as TextualMarkdown
from textual.widgets import Static


class MarkdownViewer(TextualMarkdown):
    """Расширенный Markdown viewer с улучшенным стилем.
    
    Использует textual.widgets.Markdown как базу и добавляет:
    - Кастомные стили для чата
    - Поддержку inline code
    - Улучшенный syntax highlighting
    
    Пример:
        >>> md = MarkdownViewer("# Hello\\n**Bold** text with `code`")
        >>> # Отобразит форматированный Markdown
    """
    
    DEFAULT_CSS = """
    MarkdownViewer {
        padding: 0;
        margin: 0;
    }
    
    MarkdownViewer > .code_inline {
        background: $surface;
        color: $secondary;
    }
    """
    
    def __init__(
        self,
        markdown: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует MarkdownViewer.
        
        Args:
            markdown: Markdown текст для рендеринга
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(markdown, name=name, id=id, classes=classes)


class InlineMarkdown(TextualMarkdown):
    """Компактный Markdown рендер для коротких inline текстов.
    
    Использует textual.widgets.Markdown для корректного парсинга Markdown
    без смешения уровней абстракции (Markdown → Rich markup → парсер).
    
    Преимущества перед ручной конвертацией:
    - Нет проблем с экранированием скобок
    - Нет MarkupError от литеральных Rich-тегов в тексте LLM
    - Корректная обработка всех Markdown элементов
    - Архитектурно чистое решение
    
    Пример:
        >>> text = InlineMarkdown("**Bold** and *italic* with `code`")
    """
    
    DEFAULT_CSS = """
    InlineMarkdown {
        padding: 0;
        margin: 0;
        height: auto;
    }
    
    InlineMarkdown MarkdownBlock {
        padding: 0;
        margin: 0;
    }
    
    InlineMarkdown MarkdownH1,
    InlineMarkdown MarkdownH2,
    InlineMarkdown MarkdownH3,
    InlineMarkdown MarkdownH4,
    InlineMarkdown MarkdownH5,
    InlineMarkdown MarkdownH6 {
        padding: 0;
        margin: 0;
    }
    
    InlineMarkdown MarkdownParagraph {
        padding: 0;
        margin: 0;
    }
    """
    
    def __init__(
        self,
        content: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует InlineMarkdown.
        
        Args:
            content: Markdown текст
            name: Имя виджета  
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(content, name=name, id=id, classes=classes)
        self._raw_content = content
    
    @property
    def raw_content(self) -> str:
        """Возвращает исходный Markdown текст."""
        return self._raw_content
    
    def update_content(self, content: str) -> None:
        """Обновляет контент с новым Markdown.
        
        Args:
            content: Новый Markdown текст
        """
        self._raw_content = content
        self.update(content)


class CodeBlock(Static):
    """Блок кода с syntax highlighting.
    
    Использует Rich syntax highlighting для отображения кода
    с подсветкой синтаксиса.
    
    Пример:
        >>> code = CodeBlock("def hello():\\n    print('Hi')", language="python")
    """
    
    DEFAULT_CSS = """
    CodeBlock {
        background: $surface;
        padding: 1;
        margin: 1 0;
        border: solid $primary-background;
    }
    """
    
    def __init__(
        self,
        code: str,
        language: str = "text",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        theme: str = "monokai",
    ) -> None:
        """Инициализирует CodeBlock.
        
        Args:
            code: Код для отобра
            language: Язык программирования
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
            theme: Тема подсветки (monokai для dark, github-light для light)
        """
        from rich.syntax import Syntax
        
        self._code = code
        self._language = language
        self._theme = theme
        
        # Создаем Rich Syntax объект
        syntax = Syntax(
            code,
            language,
            theme=theme,
            line_numbers=False,
            word_wrap=True,
        )
        
        super().__init__(syntax, name=name, id=id, classes=classes)
    
    @property
    def code(self) -> str:
        """Возвращает исходный код."""
        return self._code
    
    @property
    def language(self) -> str:
        """Возвращает язык программирования."""
        return self._language
    
    def update_code(self, code: str, language: str | None = None) -> None:
        """Обновляет код.
        
        Args:
            code: Новый код
            language: Новый язык (опционально)
        """
        from rich.syntax import Syntax
        
        self._code = code
        if language is not None:
            self._language = language
        
        syntax = Syntax(
            code,
            self._language,
            theme=self._theme,
            line_numbers=False,
            word_wrap=True,
        )
        self.update(syntax)
