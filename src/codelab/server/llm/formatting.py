"""Общие функции форматирования сообщений и ответов в OpenAI-формат.

Используются провайдерами, которые работают с OpenAI-совместимым
представлением сообщений (OpenAICompatibleProvider, LiteLLMProvider).
Выделены в отдельный модуль для устранения дублирования и обеспечения
единого контракта конвертации на границе с LLM-адаптерами.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from codelab.server.llm.content_parts import ContentPart
from codelab.server.llm.models import LLMMessage, LLMToolCall, StopReason


def messages_to_openai_dict(
    messages: list[LLMMessage],
    *,
    supports_vision: bool = True,
    supports_audio: bool = True,
) -> list[dict[str, Any]]:
    """Преобразовать LLMMessage в формат OpenAI Chat API.

    Args:
        messages: Список доменных сообщений.
        supports_vision: Поддерживает ли провайдер изображения; при False
            image-части отбрасываются (graceful degradation).
        supports_audio: Поддерживает ли провайдер аудио; при False
            audio-части отбрасываются.

    Returns:
        Список словарей в формате OpenAI messages API.
    """
    openai_messages: list[dict[str, Any]] = []

    for msg in messages:
        openai_msg: dict[str, Any] = {"role": msg.role}

        if msg.content is not None:
            if isinstance(msg.content, list):
                openai_msg["content"] = content_parts_to_openai(
                    msg.content,
                    supports_vision=supports_vision,
                    supports_audio=supports_audio,
                )
            else:
                openai_msg["content"] = msg.content

        if msg.role == "assistant" and msg.tool_calls:
            openai_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in msg.tool_calls
            ]

        if msg.role == "tool":
            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id
            if msg.name:
                openai_msg["name"] = msg.name

        openai_messages.append(openai_msg)

    return openai_messages


def content_parts_to_openai(
    parts: list[ContentPart],
    *,
    supports_vision: bool,
    supports_audio: bool,
) -> list[dict[str, Any]]:
    """Конвертировать ContentPart-ы в формат OpenAI content.

    Args:
        parts: Список доменных частей контента.
        supports_vision: Поддерживает ли вызывающий провайдер изображения.
        supports_audio: Поддерживает ли вызывающий провайдер аудио.

    Returns:
        Список словарей в формате OpenAI content parts.
    """
    result: list[dict[str, Any]] = []
    for part in parts:
        converted = content_part_to_openai(
            part, supports_vision=supports_vision, supports_audio=supports_audio
        )
        if converted is not None:
            result.append(converted)
    return result


def content_part_to_openai(
    part: ContentPart,
    *,
    supports_vision: bool,
    supports_audio: bool,
) -> dict[str, Any] | None:
    """Конвертировать один ContentPart в OpenAI content-элемент.

    Args:
        part: Доменная часть контента.
        supports_vision: При False image-часть возвращает None.
        supports_audio: При False audio-часть возвращает None.

    Returns:
        Словарь OpenAI content-элемента или None, если часть отброшена.
    """
    if part.type == "text":
        return {"type": "text", "text": part.text or ""}
    if part.type == "image":
        if not supports_vision:
            return None
        data = part.data or ""
        mime_type = part.mime_type or "image/png"
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{data}"},
        }
    if part.type == "audio":
        if not supports_audio:
            return None
        mime_type = part.mime_type or "audio/wav"
        fmt = _extract_audio_format(mime_type)
        return {
            "type": "input_audio",
            "input_audio": {
                "data": part.data or "",
                "format": fmt,
            },
        }
    return None


def _extract_audio_format(mime_type: str) -> str:
    if "/" in mime_type:
        return mime_type.split("/", 1)[1]
    return mime_type


def validate_openai_message_history(messages: list[dict[str, Any]]) -> None:
    """Валидировать историю сообщений в OpenAI-формате.

    Проверяет, что каждое tool-сообщение содержит tool_call_id
    и следует за assistant-сообщением с tool_calls.

    Args:
        messages: Список сообщений в формате OpenAI.

    Raises:
        ValueError: Если история некорректна.
    """
    last_assistant_tool_call_ids: set[str] = set()

    for i, msg in enumerate(messages):
        role = msg.get("role")

        if role == "assistant":
            tool_calls = msg.get("tool_calls", [])
            last_assistant_tool_call_ids = (
                {tc["id"] for tc in tool_calls} if tool_calls else set()
            )

        elif role == "tool":
            tool_call_id = msg.get("tool_call_id")

            if not tool_call_id:
                raise ValueError(f"Tool message at index {i} missing tool_call_id")

            if not last_assistant_tool_call_ids:
                raise ValueError(
                    f"Tool message at index {i} must follow an assistant "
                    f"message with tool_calls"
                )


def finish_reason_to_stop_reason(
    finish_reason: str | None,
    *,
    has_tool_calls: bool,
) -> StopReason:
    """Маппинг OpenAI finish_reason → доменный StopReason.

    В стриме finish_reason может отсутствовать (None), но при собранных
    tool_calls всё равно нужен TOOL_USE — поэтому has_tool_calls имеет
    приоритет.
    """
    if finish_reason == "tool_calls" or has_tool_calls:
        return StopReason.TOOL_USE
    if finish_reason == "length":
        return StopReason.MAX_TOKENS
    if finish_reason == "stop":
        return StopReason.STOP_SEQUENCE
    return StopReason.END_TURN


def parse_openai_tool_calls(tool_calls: Iterable[Any]) -> list[LLMToolCall]:
    """Преобразовать tool_calls ответа в доменный формат.

    Принимает Iterable[Any] (а не конкретный тип openai) для обеспечения
    совместимости с разными SDK (openai, litellm) и простого мокирования
    в тестах.

    Args:
        tool_calls: Итерируемая коллекция tool_call-объектов с полями
            id, type, function.{name, arguments}.

    Returns:
        Список доменных LLMToolCall.
    """
    result: list[LLMToolCall] = []
    for tool_call in tool_calls:
        tool_type = getattr(tool_call, "type", None)
        if tool_type is not None and tool_type != "function":
            continue
        func = getattr(tool_call, "function", None)
        if func is None:
            continue
        name = getattr(func, "name", None) or ""
        raw_args = getattr(func, "arguments", None)
        args: dict[str, Any] = {}
        if isinstance(raw_args, str):
            if raw_args:
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        result.append(
            LLMToolCall(
                id=getattr(tool_call, "id", "") or "",
                name=name,
                arguments=args,
            )
        )
    return result


def extract_openai_usage(usage: Any | None) -> dict[str, int]:
    """Нормализовать usage-объект в dict.

    Совместимо с openai.Usage и litellm-стилем usage.

    Args:
        usage: Объект с полями prompt_tokens / completion_tokens /
            total_tokens, либо None.

    Returns:
        Dict с ключами prompt_tokens, completion_tokens, total_tokens.
        Пустой dict, если usage is None.
    """
    if usage is None:
        return {}

    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    total = getattr(usage, "total_tokens", None)

    prompt_i = int(prompt) if prompt is not None else 0
    completion_i = int(completion) if completion is not None else 0

    total_i = prompt_i + completion_i if total is None else int(total)

    return {
        "prompt_tokens": prompt_i,
        "completion_tokens": completion_i,
        "total_tokens": total_i,
    }


def accumulate_tool_call_fragment(
    tool_frags: dict[int, dict[str, Any]],
    tc: Any,
) -> None:
    """Накопить фрагмент tool_call стрима по его index.

    В стриме id/name приходят в первом фрагменте, arguments — по кускам
    строки в последующих. Аккумулирует их в tool_frags in-place.

    getattr-based доступ обеспечивает совместимость с разными SDK
    (openai, litellm). index может отсутствовать или быть None — тогда 0.

    Args:
        tool_frags: Аккумулятор фрагментов по index (мутируется).
        tc: Один tool_call-delta объект стрима.
    """
    idx = getattr(tc, "index", 0) or 0
    frag = tool_frags.setdefault(idx, {"id": None, "name": None, "args": ""})
    tc_id = getattr(tc, "id", None)
    if tc_id:
        frag["id"] = tc_id
    fn = getattr(tc, "function", None)
    if fn is None:
        return
    fn_name = getattr(fn, "name", None)
    fn_args = getattr(fn, "arguments", None)
    if fn_name:
        frag["name"] = fn_name
    if fn_args:
        frag["args"] += fn_args


def assemble_tool_calls(tool_frags: dict[int, dict[str, Any]]) -> list[LLMToolCall]:
    """Собрать LLMToolCall из накопленных стрим-фрагментов.

    Args:
        tool_frags: Аккумулятор фрагментов по index.

    Returns:
        Список доменных LLMToolCall в порядке index. Фрагменты без имени
        (неполные) пропускаются; невалидный arguments-JSON → пустой dict.
    """
    result: list[LLMToolCall] = []
    for idx in sorted(tool_frags):
        frag = tool_frags[idx]
        if not frag["name"]:
            continue
        args: dict[str, Any] = {}
        if frag["args"]:
            try:
                args = json.loads(frag["args"])
            except (json.JSONDecodeError, TypeError):
                args = {}
        result.append(
            LLMToolCall(id=frag["id"] or "", name=frag["name"], arguments=args)
        )
    return result
