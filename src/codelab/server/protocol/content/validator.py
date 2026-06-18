"""Валидация content согласно ACP спецификации."""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ContentValidator:
    """Валидирует content items согласно ACP Content Types спецификации."""

    # Поддерживаемые типы content согласно спецификации
    SUPPORTED_TYPES = {"text", "diff", "image", "audio", "embedded", "resource_link"}

    # Обязательные поля для каждого типа
    REQUIRED_FIELDS = {
        "text": {"type", "text"},
        "diff": {"type", "path", "diff"},
        "image": {"type", "data", "format"},
        "audio": {"type", "data", "format"},
        "embedded": {"type", "content"},
        "resource_link": {"type", "uri"}
    }

    def validate_content_item(self, item: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Валидировать один content item.

        Args:
            item: Content item для валидации

        Returns:
            (is_valid, error_message)
        """
        # Проверить наличие type
        if "type" not in item:
            return False, "Missing 'type' field"

        content_type = item["type"]

        # Проверить поддерживаемый тип
        if content_type not in self.SUPPORTED_TYPES:
            return False, f"Unsupported content type: {content_type}"

        # Проверить обязательные поля
        required = self.REQUIRED_FIELDS.get(content_type, set())
        missing = required - set(item.keys())

        if missing:
            return False, f"Missing required fields for {content_type}: {missing}"

        return True, None

    def validate_content_list(
        self,
        content_items: list[dict[str, Any]]
    ) -> tuple[bool, list[str]]:
        """
        Валидировать список content items.

        Args:
            content_items: Список content items

        Returns:
            (all_valid, error_messages)
        """
        errors = []

        for idx, item in enumerate(content_items):
            is_valid, error = self.validate_content_item(item)
            if not is_valid:
                errors.append(f"Item {idx}: {error}")

        all_valid = len(errors) == 0

        if not all_valid:
            logger.warning(
                "content_validation_failed",
                total_items=len(content_items),
                errors=errors
            )

        return all_valid, errors

    def sanitize_content_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """
        Очистить content item, удалив неизвестные поля.

        Args:
            item: Content item

        Returns:
            Очищенный content item
        """
        content_type = item.get("type")
        if not content_type or content_type not in self.REQUIRED_FIELDS:
            return item

        # Оставить только известные поля для данного типа
        # (для безопасности и соответствия спецификации)
        required = self.REQUIRED_FIELDS[content_type]

        # Добавить опциональные поля (если есть)
        allowed = required.copy()
        if content_type == "text":
            allowed.add("annotations")
        elif content_type == "image":
            allowed.update({"width", "height", "alt_text"})

        return {k: v for k, v in item.items() if k in allowed}
