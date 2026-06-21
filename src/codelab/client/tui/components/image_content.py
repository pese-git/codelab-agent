"""Компонент ImageContentWidget для отображения изображений в чате.

Отвечает за:
- Отображение placeholder для изображений
- Показ информации о MIME типе и размере
- Визуальную индикацию наличия изображения

Примечание: В терминале невозможно отобразить реальные изображения,
поэтому используется placeholder с информацией.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class ImageContentWidget(Vertical):
    """Виджет для отображения placeholder изображения.
    
    Отображает иконку и информацию о изображении вместо реального
    контента, так как терминал не поддерживает отображение картинок.
    
    Пример:
        >>> widget = ImageContentWidget(
        ...     data="base64data...",
        ...     mime_type="image/png",
        ... )
    """
    
    DEFAULT_CSS = """
    ImageContentWidget {
        width: 100%;
        height: auto;
        padding: 1;
        margin: 1 0;
        background: $surface-darken-1;
        border: solid $primary 50%;
    }
    
    ImageContentWidget > .image-header {
        width: 100%;
        height: 1;
        text-style: bold;
        color: $primary;
    }
    
    ImageContentWidget > .image-info {
        width: 100%;
        height: auto;
        color: $text-muted;
        padding: 0 1;
    }
    
    ImageContentWidget > .image-icon {
        width: 100%;
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: $primary 70%;
    }
    """
    
    def __init__(
        self,
        data: str,
        mime_type: str,
        uri: str | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует ImageContentWidget.
        
        Args:
            data: Base64-кодированные данные изображения
            mime_type: MIME тип изображения (например, "image/png")
            uri: Опциональный URI источника изображения
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._data = data
        self._mime_type = mime_type
        self._uri = uri
    
    def compose(self) -> ComposeResult:
        """Создает структуру placeholder."""
        # Иконка изображения
        yield Static("🖼️  [IMAGE]", classes="image-icon")
        
        # Заголовок
        yield Static("Изображение", classes="image-header")
        
        # Информация о файле
        info_parts = [f"Тип: {self._mime_type}"]
        
        # Размер данных в KB/MB
        data_size = len(self._data)
        if data_size < 1024:
            info_parts.append(f"Размер: {data_size} B")
        elif data_size < 1024 * 1024:
            info_parts.append(f"Размер: {data_size / 1024:.1f} KB")
        else:
            info_parts.append(f"Размер: {data_size / (1024 * 1024):.1f} MB")
        
        if self._uri:
            info_parts.append(f"Источник: {self._uri}")
        
        yield Static(" | ".join(info_parts), classes="image-info")
    
    @property
    def mime_type(self) -> str:
        """Возвращает MIME тип изображения."""
        return self._mime_type
    
    @property
    def data_size(self) -> int:
        """Возвращает размер данных в байтах."""
        return len(self._data)
    
    @classmethod
    def from_content_block(
        cls,
        block: dict[str, Any],
        **kwargs: Any,
    ) -> ImageContentWidget:
        """Создает виджет из content block словаря.
        
        Args:
            block: Словарь с ключами type, data, mimeType, uri (опц.)
            **kwargs: Дополнительные аргументы для виджета
            
        Returns:
            Экземпляр ImageContentWidget
        """
        return cls(
            data=block.get("data", ""),
            mime_type=block.get("mimeType", "image/unknown"),
            uri=block.get("uri"),
            **kwargs,
        )
