"""Валидация ContentBlock-массива для session/prompt."""
from __future__ import annotations

from typing import Any

from ....messages import ACPMessage, JsonRpcId

# Максимальная длина текста одного промпт-блока (символов)
MAX_PROMPT_TEXT_LENGTH = 100_000

# Максимальный размер данных image в base64 (20 МБ)
MAX_IMAGE_DATA_SIZE = 20 * 1024 * 1024

# Максимальный размер данных audio в base64 (25 МБ)
MAX_AUDIO_DATA_SIZE = 25 * 1024 * 1024


def validate_prompt_content(
    request_id: JsonRpcId | None,
    prompt: list[Any],
) -> ACPMessage | None:
    """Проверяет корректность ContentBlock-массива для `session/prompt`.

    Поддерживаются типы `text`, `resource_link`, `image` и `resource`.
    При ошибке возвращается `ACPMessage.error_response`, иначе `None`.

    Пример использования:
        error = validate_prompt_content("req_1", [{"type": "text", "text": "hi"}])
    """

    for block in prompt:
        if not isinstance(block, dict):
            return ACPMessage.error_response(
                request_id,
                code=-32602,
                message="Invalid params: each prompt item must be an object",
            )
        block_type = block.get("type")
        if block_type == "text":
            if not isinstance(block.get("text"), str):
                return ACPMessage.error_response(
                    request_id,
                    code=-32602,
                    message="Invalid params: text content requires text string",
                )
            text_length = len(block["text"])
            if text_length > MAX_PROMPT_TEXT_LENGTH:
                return ACPMessage.error_response(
                    request_id,
                    code=-32602,
                    message=(
                        f"Invalid params: prompt text too long: {text_length} chars "
                        f"(max {MAX_PROMPT_TEXT_LENGTH})"
                    ),
                )
            continue
        if block_type == "resource_link":
            has_uri = isinstance(block.get("uri"), str)
            has_name = isinstance(block.get("name"), str)
            if not has_uri or not has_name:
                return ACPMessage.error_response(
                    request_id,
                    code=-32602,
                    message="Invalid params: resource_link requires uri and name",
                )
            continue
        if block_type == "image":
            data = block.get("data")
            mime_type = block.get("mimeType")
            if not isinstance(data, str) or not isinstance(mime_type, str):
                return ACPMessage.error_response(
                    request_id,
                    code=-32602,
                    message="Invalid params: image requires data (str) and mimeType (str)",
                )
            if len(data) > MAX_IMAGE_DATA_SIZE:
                return ACPMessage.error_response(
                    request_id,
                    code=-32602,
                    message=(
                        f"Invalid params: image data too large: {len(data)} bytes "
                        f"(max {MAX_IMAGE_DATA_SIZE})"
                    ),
                )
            continue
        if block_type == "audio":
            data = block.get("data")
            mime_type = block.get("mimeType")
            if not isinstance(data, str) or not isinstance(mime_type, str):
                return ACPMessage.error_response(
                    request_id,
                    code=-32602,
                    message="Invalid params: audio requires data (str) and mimeType (str)",
                )
            if len(data) > MAX_AUDIO_DATA_SIZE:
                return ACPMessage.error_response(
                    request_id,
                    code=-32602,
                    message=(
                        f"Invalid params: audio data too large: {len(data)} bytes "
                        f"(max {MAX_AUDIO_DATA_SIZE})"
                    ),
                )
            continue
        if block_type == "resource":
            resource = block.get("resource")
            if not isinstance(resource, dict):
                return ACPMessage.error_response(
                    request_id,
                    code=-32602,
                    message="Invalid params: resource requires resource object",
                )
            if not isinstance(resource.get("uri"), str):
                return ACPMessage.error_response(
                    request_id,
                    code=-32602,
                    message="Invalid params: resource requires resource.uri (str)",
                )
            continue
        return ACPMessage.error_response(
            request_id,
            code=-32602,
            message=f"Invalid params: unsupported content type {block_type}",
        )
    return None
