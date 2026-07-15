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


def _validate_text(block: dict[str, Any]) -> str | None:
    if not isinstance(block.get("text"), str):
        return "Invalid params: text content requires text string"
    text_length = len(block["text"])
    if text_length > MAX_PROMPT_TEXT_LENGTH:
        return (
            f"Invalid params: prompt text too long: {text_length} chars "
            f"(max {MAX_PROMPT_TEXT_LENGTH})"
        )
    return None


def _validate_resource_link(block: dict[str, Any]) -> str | None:
    has_uri = isinstance(block.get("uri"), str)
    has_name = isinstance(block.get("name"), str)
    if not has_uri or not has_name:
        return "Invalid params: resource_link requires uri and name"
    return None


def _validate_media(block: dict[str, Any], max_size: int, label: str) -> str | None:
    """Общая проверка image/audio: data (str) + mimeType (str) + лимит размера."""
    data = block.get("data")
    mime_type = block.get("mimeType")
    if not isinstance(data, str) or not isinstance(mime_type, str):
        return f"Invalid params: {label} requires data (str) and mimeType (str)"
    if len(data) > max_size:
        return f"Invalid params: {label} data too large: {len(data)} bytes (max {max_size})"
    return None


def _validate_resource(block: dict[str, Any]) -> str | None:
    resource = block.get("resource")
    if not isinstance(resource, dict):
        return "Invalid params: resource requires resource object"
    if not isinstance(resource.get("uri"), str):
        return "Invalid params: resource requires resource.uri (str)"
    return None


def _validate_block(block: dict[str, Any]) -> str | None:
    """Диспетчер валидации одного ContentBlock по его `type`.

    Возвращает текст ошибки или `None`, если блок корректен.
    """
    block_type = block.get("type")
    if block_type == "text":
        return _validate_text(block)
    if block_type == "resource_link":
        return _validate_resource_link(block)
    if block_type == "image":
        return _validate_media(block, MAX_IMAGE_DATA_SIZE, "image")
    if block_type == "audio":
        return _validate_media(block, MAX_AUDIO_DATA_SIZE, "audio")
    if block_type == "resource":
        return _validate_resource(block)
    return f"Invalid params: unsupported content type {block_type}"


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
        error = _validate_block(block)
        if error is not None:
            return ACPMessage.error_response(request_id, code=-32602, message=error)
    return None
