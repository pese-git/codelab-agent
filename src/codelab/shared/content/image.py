"""ImageContent для ACP протокола.

Этот модуль определяет ImageContent для передачи изображений
в виде base64-кодированных данных.

Поддерживаются основные форматы изображений: PNG, JPEG, GIF, WebP.
"""

import base64
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Допустимые MIME-типы для изображений
ALLOWED_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
}


class ImageContent(BaseModel):
    """Контент с изображением.

    Используется для передачи изображений в виде base64-кодированных данных.
    Поддерживаются основные форматы: PNG, JPEG, GIF, WebP.

    Attributes:
        type: Буквальное значение "image" для идентификации типа.
        mimeType: MIME-тип изображения (например, "image/png").
        data: Base64-кодированные данные изображения.
        uri: Опциональный URI источника изображения.
        annotations: Опциональные метаданные для обработки.

    Примеры:
        >>> content = ImageContent(
        ...     mimeType="image/png",
        ...     data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB..."
        ... )
        >>> content.type
        'image'
    """

    type: Literal["image"] = Field(default="image", description="Тип контента: image")
    mimeType: str = Field(..., description="MIME-тип изображения")
    data: str = Field(..., description="Base64-кодированные данные")
    uri: str | None = Field(None, description="Опциональный URI источника")
    annotations: dict[str, Any] | None = Field(None, description="Опциональные метаданные")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("mimeType")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Валидирует MIME-тип.

        Проверяет, что MIME-тип:
        - Не пустой
        - Соответствует разрешённому формату для изображений

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
        if mime_lower in ALLOWED_IMAGE_MIME_TYPES:
            return v

        # Проверяем по паттерну image/* для расширяемости
        if re.match(r"^image/[\w\-+.]+$", mime_lower):
            return v

        raise ValueError(
            f"mimeType '{v}' не поддерживается. Используйте "
            f"image/png, image/jpeg, image/gif, image/webp или "
            f"другой валидный image/* MIME-тип"
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

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, v: str | None) -> str | None:
        """Валидирует URI если он указан.

        Args:
            v: URI для проверки.

        Returns:
            Проверенное значение URI.

        Raises:
            ValueError: Если URI неверный.
        """
        if v is not None and not v.strip():
            raise ValueError("uri не может быть пустой строкой")
        return v
