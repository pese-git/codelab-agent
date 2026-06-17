"""TextContent для ACP протокола.

Этот модуль определяет TextContent — простой текстовый контент,
который является основным типом контента в ACP.

Текстовый контент используется для передачи сообщений от пользователя,
ответов агента, и любого другого текстового содержимого.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TextContent(BaseModel):
    """Текстовый контент.

    Используется для передачи простых текстовых сообщений. Это основной
    и наиболее часто используемый тип контента в ACP протоколе.

    Attributes:
        type: Буквальное значение "text" для идентификации типа.
        text: Текстовое содержимое. Не может быть пустым.
        annotations: Опциональные метаданные для отображения или обработки контента.

    Примеры:
        >>> content = TextContent(text="Hello, world!")
        >>> content.type
        'text'
        >>> content.model_dump()
        {'type': 'text', 'text': 'Hello, world!', 'annotations': None}
    """

    type: Literal["text"] = Field(default="text", description="Тип контента: text")
    text: str = Field(..., description="Текстовое содержимое")
    annotations: dict[str, Any] | None = Field(None, description="Опциональные метаданные")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Валидирует текст.

        Проверяет, что текст:
        - Имеет строковый тип
        - Не пустой (после удаления пробелов)

        Args:
            v: Значение текста для проверки.

        Returns:
            Проверенное значение текста.

        Raises:
            ValueError: Если текст пустой или неверного типа.
        """
        if not isinstance(v, str):
            raise ValueError("text должен быть строкой")
        if not v or not v.strip():
            raise ValueError("text не может быть пустым")
        return v
