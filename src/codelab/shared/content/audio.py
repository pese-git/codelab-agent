"""AudioContent для ACP протокола.

Этот модуль определяет AudioContent для передачи аудиоданных
в виде base64-кодированных данных.

Поддерживаются основные форматы аудио: WAV, MP3.
"""

import base64
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Допустимые MIME-типы для аудио
ALLOWED_AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/mp3",
    "audio/mpeg",
    "audio/mpeg3",
    "audio/x-mpeg-3",
}


class AudioContent(BaseModel):
    """Контент с аудиоданными.

    Используется для передачи аудиоданных в виде base64-кодированных данных.
    Поддерживаются основные форматы: WAV, MP3.

    Attributes:
        type: Буквальное значение "audio" для идентификации типа.
        mimeType: MIME-тип аудиоданных (например, "audio/wav").
        data: Base64-кодированные аудиоданные.
        annotations: Опциональные метаданные для обработки.

    Примеры:
        >>> content = AudioContent(
        ...     mimeType="audio/wav",
        ...     data="UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAAB..."
        ... )
        >>> content.type
        'audio'
    """

    type: Literal["audio"] = Field(default="audio", description="Тип контента: audio")
    mimeType: str = Field(..., description="MIME-тип аудиоданных")
    data: str = Field(..., description="Base64-кодированные данные")
    annotations: dict[str, Any] | None = Field(None, description="Опциональные метаданные")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("mimeType")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Валидирует MIME-тип.

        Проверяет, что MIME-тип:
        - Не пустой
        - Соответствует разрешённому формату для аудио

        Args:
            v: MIME-тип для проверки.

        Returns:
            Проверенное значение MIME-типа.

        Raises:
            ValueError: Если MIME-тип неверный.
        """
        if not v or not v.strip():
            raise ValueError("mimeType не может быть пустым")

        # Нормализуем для проверки
        mime_lower = v.lower()

        # Проверяем точное совпадение с известными типами
        if mime_lower in ALLOWED_AUDIO_MIME_TYPES:
            return v

        # Проверяем по паттерну audio/* для расширяемости
        if re.match(r"^audio/[\w\-+.]+$", mime_lower):
            return v

        raise ValueError(
            f"mimeType '{v}' не поддерживается. Используйте "
            f"audio/wav, audio/mp3, audio/mpeg или другой валидный "
            f"audio/* MIME-тип"
        )

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: str) -> str:
        """Валидирует base64-кодированные данные.

        Проверяет, что данные:
        - Не пустые
        - Валидная base64-строка

        Args:
            v: Base64-строка для проверки.

        Returns:
            Проверенное значение данных.

        Raises:
            ValueError: Если данные неверные.
        """
        if not v or not v.strip():
            raise ValueError("data не может быть пустым")

        # Пытаемся декодировать base64
        try:
            # Добавляем недостающие знаки '=' для выравнивания
            padding = len(v) % 4
            v_padded = v + "=" * (4 - padding) if padding else v

            base64.b64decode(v_padded, validate=True)
        except Exception as e:
            raise ValueError(f"data не является валидной base64: {e}") from e

        return v
