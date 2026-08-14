"""Проекция LLM-истории из журнала сессии (шаг 4f ADR-008).

Журнал — единственный источник, `history` — вид: чистая функция от списка
событий. Инвариант, ради которого шаг делался: **проекцию можно выбросить и
пересчитать**, поэтому здесь нет ни состояния, ни обращений к носителю.

Проекция стала возможной только после того, как журнал начал описывать каждый
факт диалога целиком, и каждая недостача находилась замером, а не рассуждением:

* текст ответа модели не выводится из ACP-контента вызова (шаг 4d) —
  `ToolCallAnswered`;
* граница сообщения не выводится из потока событий (шаг 4e) — событие на
  сообщение с обеих сторон, вместе с `tool_calls` в терминах модели.

Домен, а не `mapping`: и вход (события), и выход (сообщения) — доменные
сущности, форма wire здесь не нужна вовсе. Разбор записи с диска остаётся за
`JournalMapper`.
"""

from __future__ import annotations

from collections.abc import Iterable

from .conversation import ConversationMessage, MessageContent
from .journal import (
    AgentMessageRecorded,
    JournalEntry,
    ToolCallAnswered,
    UserMessageRecorded,
)
from .tool_call import ToolCall
from .value_objects import MessageRole

__all__ = ["project_history"]


def project_history(entries: Iterable[JournalEntry]) -> list[ConversationMessage]:
    """Собрать LLM-историю из журнала.

    События, не относящиеся к диалогу, пропускаются молча — это не потеря:
    статус вызова адресован клиенту, а модель узнаёт исход из ответа
    `role: tool`, который описан своим событием.

    Метка времени берётся из журнала. У `role: tool` её нет и в записи истории,
    поэтому она не синтезируется: `None` обязан оставаться `None`.

    Args:
        entries: Записи журнала в исходном порядке.

    Returns:
        Сообщения в том порядке, в каком они произошли.
    """
    messages: list[ConversationMessage] = []

    for entry in entries:
        match entry.event:
            case UserMessageRecorded(blocks=blocks):
                messages.append(
                    ConversationMessage(
                        role=MessageRole.USER,
                        content=MessageContent.from_acp_blocks(blocks),
                        timestamp=entry.timestamp,
                    )
                )
            case AgentMessageRecorded(content=content, tool_calls=tool_calls):
                messages.append(
                    ConversationMessage(
                        role=MessageRole.ASSISTANT,
                        content=MessageContent.from_text(
                            content.get("text", "") if content else ""
                        ),
                        timestamp=entry.timestamp,
                        tool_calls=[
                            ToolCall(
                                id=call.id,
                                tool_name=call.name,
                                arguments=call.arguments,
                            )
                            for call in tool_calls
                        ],
                    )
                )
            case ToolCallAnswered(tool_call_id=tool_call_id, text=text):
                messages.append(
                    ConversationMessage(
                        role=MessageRole.TOOL,
                        content=MessageContent.from_text(text),
                        tool_call_id=tool_call_id,
                    )
                )

    return messages
