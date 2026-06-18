"""Форматирование content для различных LLM провайдеров."""

from typing import Any, Literal

import structlog

from codelab.server.protocol.content.extractor import ExtractedContent

logger = structlog.get_logger(__name__)


class ContentFormatter:
    """Форматирует content для отправки в LLM провайдеры."""

    def format_for_llm(
        self,
        extracted_content: ExtractedContent,
        provider: Literal["openai", "anthropic"] = "openai",
    ) -> dict[str, Any]:
        """
        Форматировать content для конкретного LLM провайдера.

        Args:
            extracted_content: Извлеченный content из tool result
            provider: Тип LLM провайдера

        Returns:
            Отформатированный content для LLM
        """
        if provider == "openai":
            return self._format_for_openai(extracted_content)
        elif provider == "anthropic":
            return self._format_for_anthropic(extracted_content)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _format_for_openai(
        self,
        extracted_content: ExtractedContent,
    ) -> dict[str, Any]:
        """
        Форматировать для OpenAI API.

        OpenAI format:
        {
            "role": "tool",
            "tool_call_id": "...",
            "content": "text string or JSON"
        }
        """
        # Объединить все content items в один текст
        content_text = self._merge_content_items(extracted_content.content_items)

        return {
            "role": "tool",
            "tool_call_id": extracted_content.tool_call_id,
            "content": content_text,
        }

    def _format_for_anthropic(
        self,
        extracted_content: ExtractedContent,
    ) -> dict[str, Any]:
        """
        Форматировать для Anthropic API.

        Anthropic format:
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "...", "content": "..."}
            ]
        }
        """
        content_text = self._merge_content_items(extracted_content.content_items)

        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": extracted_content.tool_call_id,
                    "content": content_text,
                }
            ],
        }

    def _merge_content_items(
        self,
        content_items: list[dict[str, Any]],
    ) -> str:
        """
        Объединить content items в один текст для LLM.

        Args:
            content_items: Список content items

        Returns:
            Объединенный текст
        """
        parts = []

        for item in content_items:
            content_type = item.get("type")

            if content_type == "text":
                parts.append(item["text"])

            elif content_type == "diff":
                # Форматировать diff для читаемости
                path = item["path"]
                diff = item["diff"]
                parts.append(f"File: {path}\n\nDiff:\n```diff\n{diff}\n```")

            elif content_type == "image":
                # Для изображений добавить описание (LLM не видит изображения напрямую)
                alt_text = item.get("alt_text", "Image")
                format_type = item.get("format", "unknown")
                parts.append(f"[Image: {alt_text} ({format_type})]")

            elif content_type == "audio":
                # Для аудио добавить описание
                format_type = item.get("format", "unknown")
                parts.append(f"[Audio file ({format_type})]")

            elif content_type == "embedded":
                # Рекурсивно обработать embedded content
                embedded = item.get("content", [])
                if isinstance(embedded, list):
                    embedded_text = self._merge_content_items(embedded)
                    parts.append(f"[Embedded content]\n{embedded_text}")

            elif content_type == "resource_link":
                # Добавить ссылку
                uri = item.get("uri", "")
                parts.append(f"[Resource: {uri}]")

        return "\n\n".join(parts)

    def format_batch_for_llm(
        self,
        extracted_contents: list[ExtractedContent],
        provider: Literal["openai", "anthropic"] = "openai",
    ) -> list[dict[str, Any]]:
        """
        Форматировать несколько content items для LLM.

        Args:
            extracted_contents: Список извлеченных content
            provider: Тип LLM провайдера

        Returns:
            Список отформатированных messages для LLM
        """
        formatted = []

        for content in extracted_contents:
            formatted_msg = self.format_for_llm(content, provider)
            formatted.append(formatted_msg)

        logger.debug(
            "batch_formatting_complete",
            total=len(formatted),
            provider=provider,
        )

        return formatted
