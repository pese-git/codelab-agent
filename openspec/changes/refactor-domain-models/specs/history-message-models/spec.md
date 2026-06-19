# Spec: history-message-models

## ADDED Requirements

### Requirement: Domain ConversationMessage

Система ДОЛЖНА предоставлять `ConversationMessage` как frozen dataclass:
- `role: MessageRole` — роль (USER, ASSISTANT, SYSTEM, TOOL)
- `content: MessageContent` — содержимое сообщения
- `timestamp: datetime` — время создания
- `tool_calls: list[ToolCall]` — tool calls (для ASSISTANT)
- `tool_call_id: str | None` — ID tool call (для TOOL)

### Requirement: Domain MessageContent

Система ДОЛЖНА предоставлять `MessageContent` как frozen dataclass:
- `text: str` — текстовое содержимое
- `resources: list[Resource]` — встроенные ресурсы
- `images: list[Image]` — изображения

### Requirement: MessageRole Domain Enum

Система ДОЛЖНА предоставлять domain enum `MessageRole`:
- `USER` — сообщение пользователя
- `ASSISTANT` — сообщение ассистента
- `SYSTEM` — системное сообщение
- `TOOL` — результат tool call

### Requirement: HistoryMessage ACP Protocol Model

Система ДОЛЖНА обновить `HistoryMessage` как ACP Protocol Model:
- `role: str` — роль (ACP format)
- `content: list[ContentBlock] | str` — содержимое
- `timestamp: str | None` — время создания (ISO format)
- `tool_calls: list[ToolCallState] | None` — tool calls
- `tool_call_id: str | None` — ID tool call

### Requirement: HistoryMessage Docstring

`HistoryMessage` ДОЛЖЕН иметь docstring с пометкой:
```python
"""ACP Protocol Model — контракт сообщения истории согласно ACP 05-Prompt Turn.

Wire format для хранения истории сообщений в SessionState.

НЕ является domain моделью. Для бизнес-логики использовать domain ConversationMessage.
Конвертация через HistoryMapper.
"""
```

### Requirement: HistoryMapper

Система ДОЛЖНА предоставлять `HistoryMapper` с методами:
- `to_protocol(domain: ConversationMessage) -> HistoryMessage`
- `to_domain(protocol: HistoryMessage) -> ConversationMessage`

### Requirement: Замена union типов

Система ДОЛЖНА убрать union типы из `HistoryMessage.content` через маппинг с domain моделью.
