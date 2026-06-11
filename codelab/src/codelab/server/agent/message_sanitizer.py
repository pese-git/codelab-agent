"""MessageSanitizer — исправление orphaned tool calls в истории.

Рефакторинг из AgentOrchestrator._sanitize_orphaned_tool_calls().
Добавляет синтетические error-результаты для потерянных tool_calls.
"""

from __future__ import annotations

from codelab.server.llm.models import LLMMessage


class MessageSanitizer:
    """Исправляет orphaned tool calls в истории сообщений.

    Если assistant message имеет tool_calls, но соответствующих
    tool responses нет, добавляет синтетические error-результаты.
    """

    def sanitize(self, messages: list[LLMMessage]) -> list[LLMMessage]:
        """Исправить orphaned tool calls.

        Args:
            messages: Список сообщений из истории.

        Returns:
            Список сообщений с добавленными заглушками для осиротевших tool_calls.
        """
        result: list[LLMMessage] = []
        orphaned_count = 0
        i = 0

        while i < len(messages):
            msg = messages[i]
            if msg.role == "assistant" and msg.tool_calls:
                expected_ids = {tc.id for tc in msg.tool_calls}
                j = i + 1
                tool_msgs: list[LLMMessage] = []
                while j < len(messages) and messages[j].role == "tool":
                    tool_msgs.append(messages[j])
                    j += 1
                satisfied_ids = {
                    m.tool_call_id for m in tool_msgs if m.tool_call_id
                }
                orphaned_ids = expected_ids - satisfied_ids
                result.append(msg)
                result.extend(tool_msgs)
                for oid in orphaned_ids:
                    orphaned_count += 1
                    result.append(
                        LLMMessage(
                            role="tool",
                            content="Error: Tool execution did not complete",
                            tool_call_id=oid,
                        )
                    )
                i = j
            else:
                result.append(msg)
                i += 1

        return result
