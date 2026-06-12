"""HistoryBuilder — конвертация session history в LLMMessage.

Поддерживает различные форматы записей истории и добавление system prompt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from codelab.server.llm.models import LLMMessage, LLMToolCall

if TYPE_CHECKING:
    pass


class HistoryBuilder:
    """Конвертирует session history в список LLMMessage для LLM.

    Поддерживает форматы:
    - {"role": "user", "content": list[block] | str}
    - {"role": "user", "text": str}
    - {"role": "assistant", "text": str, "tool_calls"?: [...]}
    - {"role": "tool", "tool_call_id": str, "content": str}
    """

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
            entry_dict: dict[str, Any]
            if isinstance(entry, dict):
                entry_dict = entry
            elif hasattr(entry, "model_dump"):
                entry_dict = entry.model_dump()
            else:
                continue

            role = entry_dict.get("role", "user")
            if role not in ("system", "user", "assistant", "tool"):
                role = "user"

            # tool результаты
            if role == "tool":
                messages.append(
                    LLMMessage(
                        role="tool",
                        content=str(entry_dict.get("content", "")),
                        tool_call_id=entry_dict.get("tool_call_id"),
                        name=entry_dict.get("name"),
                    )
                )
                continue

            # assistant с tool_calls
            tool_calls_data = entry_dict.get("tool_calls")
            if role == "assistant" and tool_calls_data:
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
                messages.append(
                    LLMMessage(
                        role="assistant",
                        content=str(
                            entry_dict.get("text", "")
                            or entry_dict.get("content", "")
                            or ""
                        ),
                        tool_calls=llm_tool_calls if llm_tool_calls else None,
                    )
                )
                continue

            # Обычные сообщения (user / assistant без tool_calls)
            content = entry_dict.get("text", "") or entry_dict.get("content", "")
            # content может быть list[dict] (prompt blocks) — конвертируем в str
            if isinstance(content, list):
                content = " ".join(
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            if content:
                messages.append(LLMMessage(role=role, content=str(content)))

        return messages
