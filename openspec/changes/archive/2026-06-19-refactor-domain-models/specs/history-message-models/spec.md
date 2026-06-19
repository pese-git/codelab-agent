# Spec: history-message-models

## ADDED Requirements

### Requirement: Domain ConversationMessage

Система SHALL предоставлять `ConversationMessage` как frozen dataclass:
- `role: MessageRole` — роль (USER, ASSISTANT, SYSTEM, TOOL)
- `content: MessageContent` — содержимое сообщения
- `timestamp: datetime` — время создания
- `tool_calls: list[ToolCall]` — tool calls (для ASSISTANT)
- `tool_call_id: str | None` — ID tool call (для TOOL)

#### Scenario: Создание ConversationMessage
- **WHEN** создается ConversationMessage
- **THEN** объект содержит поля `role`, `content`, `timestamp`, `tool_calls`, `tool_call_id`

#### Scenario: ConversationMessage как frozen dataclass
- **WHEN** создан ConversationMessage объект
- **THEN** его поля нельзя изменить (immutable)

### Requirement: Domain MessageContent

Система SHALL предоставлять `MessageContent` как frozen dataclass:
- `text: str` — текстовое содержимое
- `resources: list[Resource]` — встроенные ресурсы
- `images: list[Image]` — изображения

#### Scenario: Создание MessageContent
- **WHEN** создается MessageContent
- **THEN** объект содержит поля `text`, `resources`, `images`

### Requirement: MessageRole Domain Enum

Система SHALL предоставлять domain enum `MessageRole`:
- `USER` — сообщение пользователя
- `ASSISTANT` — сообщение ассистента
- `SYSTEM` — системное сообщение
- `TOOL` — результат tool call

#### Scenario: Использование MessageRole
- **WHEN** используется MessageRole
- **THEN** доступны значения USER, ASSISTANT, SYSTEM, TOOL

### Requirement: HistoryMessage ACP Protocol Model

Система SHALL обновить `HistoryMessage` как ACP Protocol Model:
- `role: str` — роль (ACP format)
- `content: list[ContentBlock] | str` — содержимое
- `timestamp: str | None` — время создания (ISO format)
- `tool_calls: list[ToolCallState] | None` — tool calls
- `tool_call_id: str | None` — ID tool call

#### Scenario: HistoryMessage как ACP Protocol Model
- **WHEN** используется HistoryMessage
- **THEN** он соответствует ACP спецификации для хранения истории сообщений

### Requirement: HistoryMessage Docstring

`HistoryMessage` SHALL иметь docstring с пометкой:
```python
"""ACP Protocol Model — контракт сообщения истории согласно ACP 05-Prompt Turn.

Wire format для хранения истории сообщений в SessionState.

НЕ является domain моделью. Для бизнес-логики использовать domain ConversationMessage.
Конвертация через HistoryMapper.
"""
```

#### Scenario: Docstring для HistoryMessage
- **WHEN** определен HistoryMessage
- **THEN** он содержит docstring с пометкой "ACP Protocol Model"

### Requirement: HistoryMapper

Система SHALL предоставлять `HistoryMapper` с методами:
- `to_protocol(domain: ConversationMessage) -> HistoryMessage`
- `to_domain(protocol: HistoryMessage) -> ConversationMessage`

#### Scenario: Конвертация domain в protocol
- **WHEN** вызывается `HistoryMapper.to_protocol()` с ConversationMessage
- **THEN** возвращается HistoryMessage

#### Scenario: Конвертация protocol в domain
- **WHEN** вызывается `HistoryMapper.to_domain()` с HistoryMessage
- **THEN** возвращается ConversationMessage

### Requirement: Замена union типов

Система SHALL убрать union типы из `HistoryMessage.content` через маппинг с domain моделью.

#### Scenario: Типизированный content в ConversationMessage
- **WHEN** используется ConversationMessage
- **THEN** поле `content` имеет тип `MessageContent` вместо union типов
