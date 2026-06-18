"""EmbeddedResourceContent для ACP протокола.

Этот модуль определяет EmbeddedResourceContent для встраивания
содержимого ресурсов прямо в сообщение (текстовых или бинарных).

Это предпочтительный способ передачи контекста через @-mentions
и подобные механизмы.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from codelab.shared.content.base import BlobResource, TextResource


class EmbeddedResourceContent(BaseModel):
    """Контент с встроенным ресурсом.

    Используется для встраивания полного содержимого ресурса (текста или бинарных данных)
    прямо в сообщение. Это предпочтительный способ для включения контекста в промпты
    через @-mentions и подобные механизмы.

    Attributes:
        type: Буквальное значение "resource" для идентификации типа.
        resource: Встроенный ресурс (TextResource или BlobResource).
        annotations: Опциональные метаданные для обработки.

    Примеры:
        >>> from codelab.shared.content.base import TextResource
        >>> content = EmbeddedResourceContent(
        ...     resource=TextResource(
        ...         uri="file:///script.py",
        ...         text="def hello():\\n    print('hello')",
        ...         mimeType="text/x-python"
        ...     )
        ... )
        >>> content.type
        'resource'
    """

    type: Literal["resource"] = Field(default="resource", description="Тип контента: resource")
    resource: TextResource | BlobResource = Field(
        ..., description="Встроенный ресурс (TextResource или BlobResource)"
    )
    annotations: dict[str, Any] | None = Field(None, description="Опциональные метаданные")

    model_config = ConfigDict(
        populate_by_name=True,
        # discriminator не используется — определяем тип вручную в валидаторе
    )

    @field_validator("resource", mode="before")
    @classmethod
    def validate_resource(cls, v: Any) -> TextResource | BlobResource:
        """Валидирует встроенный ресурс.

        Проверяет, что ресурс является либо TextResource, либо BlobResource,
        и что он содержит валидные данные. Автоматически определяет тип
        ресурса по наличию ключей 'text' или 'blob'.

        Args:
            v: Ресурс для проверки (может быть dict или объект).

        Returns:
            Проверенный ресурс (TextResource или BlobResource).

        Raises:
            ValueError: Если ресурс неверный.
        """
        # Если уже правильный тип — возвращаем как есть
        if isinstance(v, (TextResource, BlobResource)):
            return v

        # Если dict — определяем тип по наличию ключей
        if isinstance(v, dict):
            if "blob" in v:
                # BlobResource имеет ключ 'blob'
                return BlobResource.model_validate(v)
            elif "text" in v:
                # TextResource имеет ключ 'text'
                return TextResource.model_validate(v)
            else:
                raise ValueError(
                    "Ресурс должен содержать либо 'text' "
                    "(для TextResource), либо 'blob' (для BlobResource)"
                )

        raise ValueError(
            f"resource должен быть dict, TextResource или BlobResource, получено {type(v)}"
        )
