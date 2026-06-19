# Spec: history-message-models

## ДОБАВЛЕННЫЕ Требования

### Требование: Domain ConversationMessage

Система ДОЛЖНА предоставлять `ConversationMessage` как frozen dataclass:
- `role: MessageRole` — роль (USER, ASSISTANT, SYSTEM, TOOL)
- `content: MessageContent` — содержимое сообщения
- `timestamp: datetime` — время создания
- `tool_calls: list[ToolCall]` — tool calls (для ASSISTANT)
- `tool_call_id: str | None` — ID tool call (для TOOL)

### Требование: Domain MessageContent

Система ДОЛЖНА предоставлять `MessageContent` как frozen dataclass:
- `text: str` — текстовое содержимое
- `resources: list[Resource]` — встроенные ресурсы
- `images: list[Image]` — изображения

### Требование: MessageRole Domain Enum

Система ДОЛЖНА предоставлять domain enum `MessageRole`:
- `USER` — сообщение пользователя
- `ASSISTANT` — сообщение ассистента
- `SYSTEM` — системное сообщение
- `TOOL` — результат tool call

### Требование: HistoryMessageDTO для ACP

Система ДОЛЖНА предоставлять `HistoryMessageDTO` как Pydantic модель:
- `role: str` — роль (ACP format)
- `content: list[ContentBlockDTO] | str` — содержимое
- `timestamp: str | None` — время создания (ISO format)
- `tool_calls: list[ToolCallDTO] | None` — tool calls
- `tool_call_id: str | None` — ID tool call

### Требование: HistoryMapper

Система ДОЛЖНА предоставлять `HistoryMapper` с методами:
- `to_dto(domain: ConversationMessage) -> HistoryMessageDTO`
- `to_domain(dto: HistoryMessageDTO) -> ConversationMessage`

### Требование: Замена HistoryMessage

Система ДОЛЖНА заменить `HistoryMessage` на `HistoryMessageDTO` в `SessionState`.
