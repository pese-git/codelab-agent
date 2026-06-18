"""ResourceLinkContent для ACP протокола.

Этот модуль определяет ResourceLinkContent для создания ссылок
на ресурсы, доступные агенту.

В отличие от EmbeddedResourceContent, содержимое ресурса не встраивается
в сообщение — передаётся только ссылка и метаданные.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResourceLinkContent(BaseModel):
    """Контент со ссылкой на ресурс.

    Используется для создания ссылок на ресурсы, доступные агенту.
    Может содержать метаинформацию о ресурсе (название, описание, размер и т.д.).

    В отличие от EmbeddedResourceContent, фактическое содержимое ресурса
    не передаётся — агент может запросить его отдельно при необходимости.

    Attributes:
        type: Буквальное значение "resource_link" для идентификации типа.
        uri: Универсальный идентификатор ресурса (обязательно).
        name: Человеко-читаемое имя ресурса (обязательно).
        mimeType: Опциональный MIME-тип ресурса.
        title: Опциональный заголовок для отображения.
        description: Опциональное описание контента.
        size: Опциональный размер в байтах.
        annotations: Опциональные метаданные для обработки.

    Примеры:
        >>> content = ResourceLinkContent(
        ...     uri="file:///document.pdf",
        ...     name="document.pdf",
        ...     mimeType="application/pdf",
        ...     size=1024000
        ... )
        >>> content.type
        'resource_link'
    """

    type: Literal["resource_link"] = Field(
        default="resource_link", description="Тип контента: resource_link"
    )
    uri: str = Field(..., description="URI ресурса")
    name: str = Field(..., description="Человеко-читаемое имя ресурса")
    mimeType: str | None = Field(None, description="MIME-тип ресурса (опционально)")
    title: str | None = Field(None, description="Заголовок для отображения")
    description: str | None = Field(None, description="Описание контента")
    size: int | None = Field(None, description="Размер в байтах")
    annotations: dict[str, Any] | None = Field(None, description="Опциональные метаданные")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, v: str) -> str:
        """Валидирует URI.

        Проверяет, что URI:
        - Не пустой

        Args:
            v: URI для проверки.

        Returns:
            Проверенное значение URI.

        Raises:
            ValueError: Если URI неверный.
        """
        if not v or not v.strip():
            raise ValueError("uri не может быть пустым")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Валидирует имя ресурса.

        Проверяет, что имя:
        - Не пустое

        Args:
            v: Имя для проверки.

        Returns:
            Проверенное значение имени.

        Raises:
            ValueError: Если имя неверное.
        """
        if not v or not v.strip():
            raise ValueError("name не может быть пустым")
        return v

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: int | None) -> int | None:
        """Валидирует размер ресурса.

        Проверяет, что размер:
        - Не отрицательный (если указан)

        Args:
            v: Размер для проверки.

        Returns:
            Проверенное значение размера.

        Raises:
            ValueError: Если размер неверный.
        """
        if v is not None and v < 0:
            raise ValueError("size не может быть отрицательным")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        """Валидирует заголовок если он указан.

        Args:
            v: Заголовок для проверки.

        Returns:
            Проверенное значение заголовка.

        Raises:
            ValueError: Если заголовок неверный.
        """
        if v is not None and not isinstance(v, str):
            raise ValueError("title должен быть строкой")
        if v is not None and not v.strip():
            raise ValueError("title не может быть пустой строкой")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        """Валидирует описание если оно указано.

        Args:
            v: Описание для проверки.

        Returns:
            Проверенное значение описания.

        Raises:
            ValueError: Если описание неверное.
        """
        if v is not None and not isinstance(v, str):
            raise ValueError("description должен быть строкой")
        if v is not None and not v.strip():
            raise ValueError("description не может быть пустой строкой")
        return v

    @field_validator("mimeType")
    @classmethod
    def validate_mime_type(cls, v: str | None) -> str | None:
        """Валидирует MIME-тип если он указан.

        Args:
            v: MIME-тип для проверки.

        Returns:
            Проверенное значение MIME-типа.

        Raises:
            ValueError: Если MIME-тип неверный.
        """
        if v is not None and not v.strip():
            raise ValueError("mimeType не может быть пустой строкой")
        return v
