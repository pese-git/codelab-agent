"""Компонент AudioContentWidget для отображения аудио в чате.

Отвечает за:
- Отображение placeholder для аудио
- Показ информации о MIME типе и размере
- Визуальную индикацию наличия аудио

Примечание: В терминале невозможно воспроизвести аудио,
поэтому используется placeholder с информацией.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class AudioContentWidget(Vertical):
    """Виджет для отображения placeholder аудио.
    
    Отображает иконку и информацию об аудио файле вместо реального
    контента, так как терминал не поддерживает воспроизведение звука.
    
    Пример:
        >>> widget = AudioContentWidget(
        ...     data="base64data...",
        ...     mime_type="audio/wav",
        ... )
    """
    
    DEFAULT_CSS = """
    AudioContentWidget {
        width: 100%;
        height: auto;
        padding: 1;
        margin: 1 0;
        background: $surface-darken-1;
        border: solid $secondary 50%;
    }
    
    AudioContentWidget > .audio-header {
        width: 100%;
        height: 1;
        text-style: bold;
        color: $secondary;
    }
    
    AudioContentWidget > .audio-info {
        width: 100%;
        height: auto;
        color: $text-muted;
        padding: 0 1;
    }
    
    AudioContentWidget > .audio-icon {
        width: 100%;
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: $secondary 70%;
    }
    """
    
    def __init__(
        self,
        data: str,
        mime_type: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Инициализирует AudioContentWidget.
        
        Args:
            data: Base64-кодированные данные аудио
            mime_type: MIME тип аудио (например, "audio/wav")
            name: Имя виджета
            id: ID виджета
            classes: CSS классы
        """
        super().__init__(name=name, id=id, classes=classes)
        self._data = data
        self._mime_type = mime_type
    
    def compose(self) -> ComposeResult:
        """Создает структуру placeholder."""
        # Иконка аудио
        yield Static("🔊  [AUDIO]", classes="audio-icon")
        
        # Заголовок
        yield Static("Аудио", classes="audio-header")
        
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
        
        yield Static(" | ".join(info_parts), classes="audio-info")
    
    @property
    def mime_type(self) -> str:
        """Возвращает MIME тип аудио."""
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
    ) -> AudioContentWidget:
        """Создает виджет из content block словаря.
        
        Args:
            block: Словарь с ключами type, data, mimeType
            **kwargs: Дополнительные аргументы для виджета
            
        Returns:
            Экземпляр AudioContentWidget
        """
        return cls(
            data=block.get("data", ""),
            mime_type=block.get("mimeType", "audio/unknown"),
            **kwargs,
        )
