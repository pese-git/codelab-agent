"""HistoryBuilder — конвертация session history в LLMMessage.

Поддерживает различные форматы записей истории и добавление system prompt.

ADR-005 Фаза 2: ``HistoryBuilder`` принимает ``ContentCodec`` через DI
(вместо хардкода ``ACPContentMapper``). ACP-реализация
``ACPContentCodec`` живёт в ``protocol/content/acp_codec.py``.
Default codec — ``ACPContentCodec`` (через ``from_dict``-совместимый
``map_blocks``). Для unit-тестов можно инжектить
``FakeContentCodec`` (см. tests/server/agent/fakes/content_codec.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from codelab.server.llm.content_parts import ContentPart
from codelab.server.llm.models import LLMMessage, LLMToolCall
from codelab.server.protocol.content.acp_codec import ACPContentCodec

if TYPE_CHECKING:
    from codelab.server.agent.contracts.ports import ContentCodec


class HistoryBuilder:
    """Конвертирует session history в список LLMMessage для LLM.

    Поддерживает форматы:
    - {"role": "user", "content": list[block] | str}
    - {"role": "user", "text": str}
    - {"role": "assistant", "text": str, "tool_calls"?: [...]}
    - {"role": "tool", "tool_call_id": str, "content": str}
    """

    def __init__(self, codec: ContentCodec | None = None) -> None:
        """Инициализация HistoryBuilder.

        Args:
            codec: Реализация ``ContentCodec`` для декодирования
                content-блоков. По умолчанию — ``ACPContentCodec``
                (ACP-форма). Инжектируется для unit-тестов и для
                альтернативных драйверов (A2A, тест-харнесс).
        """
        self._codec: ContentCodec = codec or ACPContentCodec()

    def build(
        self,
        history: list[dict[str, Any]] | list,
        system_prompt: str | None = None,
    ) -> list[LLMMessage]:
        """Собрать LLMMessage из истории.

        Args:
            history: Записи из SessionState.history.
            system_prompt: Системный промпт (добавляется первым сообщением).

        Returns:
            Список LLMMessage для передачи в LLM провайдер.
        """
        messages: list[LLMMessage] = []

        # System prompt первым сообщением
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))

        # Конвертируем историю
        messages.extend(self._convert_to_llm_messages(history))

        return messages

    def _convert_to_llm_messages(
        self,
        history: list[dict[str, Any]] | list,
    ) -> list[LLMMessage]:
        """Конвертировать записи истории в LLMMessage."""
        messages: list[LLMMessage] = []

        for entry in history:
            message = self._convert_history_entry(entry)
            if message is not None:
                messages.append(message)

        return messages

    @staticmethod
    def _extract_llm_tool_calls(tool_calls_data: Any) -> list[LLMToolCall]:
        """Конвертирует сырые tool_calls (dict/объект) в список LLMToolCall."""
        llm_tool_calls: list[LLMToolCall] = []
        for tc in tool_calls_data:
            if isinstance(tc, dict):
                llm_tool_calls.append(
                    LLMToolCall(
                        id=tc.get("id", ""),
                        name=tc.get("name", ""),
                        arguments=tc.get("arguments", {}),
                    )
                )
            elif hasattr(tc, "id"):
                llm_tool_calls.append(tc)
        return llm_tool_calls

    def _convert_history_entry(self, entry: Any) -> LLMMessage | None:
        """Конвертирует одну запись истории в LLMMessage (или None, если пропустить)."""
        if isinstance(entry, dict):
            entry_dict = entry
        elif hasattr(entry, "model_dump"):
            entry_dict = entry.model_dump()
        else:
            return None

        role = entry_dict.get("role", "user")
        if role not in ("system", "user", "assistant", "tool"):
            role = "user"

        # tool результаты
        if role == "tool":
            return LLMMessage(
                role="tool",
                content=str(entry_dict.get("content", "")),
                tool_call_id=entry_dict.get("tool_call_id"),
                name=entry_dict.get("name"),
            )

        # assistant с tool_calls
        tool_calls_data = entry_dict.get("tool_calls")
        if role == "assistant" and tool_calls_data:
            llm_tool_calls = self._extract_llm_tool_calls(tool_calls_data)
            return LLMMessage(
                role="assistant",
                content=str(entry_dict.get("text", "") or entry_dict.get("content", "") or ""),
                tool_calls=llm_tool_calls if llm_tool_calls else None,
            )

        # Обычные сообщения (user / assistant без tool_calls)
        content = entry_dict.get("text", "") or entry_dict.get("content", "")
        # content может быть list[dict] (prompt blocks) — конвертируем
        if isinstance(content, list):
            content = self._convert_content_blocks(content)
        if content:
            return LLMMessage(role=role, content=content)  # type: ignore[arg-type]
        return None

    def _convert_content_blocks(
        self,
        blocks: list[dict[str, Any]],
    ) -> str | list[ContentPart]:
        """Конвертировать блоки содержимого через инжектированный ``ContentCodec``.

        Если есть мультимодальные блоки — вернуть list[ContentPart].
        Если только текст — схлопнуть в строку (обратная совместимость).
        """
        parts = self._codec.decode(blocks)
        if not parts:
            return ""

        has_multimodal = any(p.is_multimodal for p in parts)
        if has_multimodal:
            return parts

        # Только текст — схлопнуть в строку
        return " ".join(p.text for p in parts if p.text)
