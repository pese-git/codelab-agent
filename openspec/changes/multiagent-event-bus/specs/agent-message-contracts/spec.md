# Spec: agent-message-contracts

## ДОБАВЛЕННЫЕ Требования

### Требование: Контракт AgentRequest

Система ДОЛЖНА определять `AgentRequest` как frozen dataclass с полями:
- `target_agent: str` — имя целевого агента
- `messages: list[Message]` — история сообщений для LLM
- `tools: list[ToolDefinition]` — доступные инструменты
- `correlation_id: str` — ID для tracing
- `session_id: str` — ID сессии

### Требование: Контракт AgentResponse

Система ДОЛЖНА определять `AgentResponse` как frozen dataclass с полями:
- `request_id: str` — ID запроса
- `text: str` — текстовый ответ
- `tool_calls: list[ToolCall]` — запрошенные tool calls
- `usage: TokenUsage` — информация о токенах
- `stop_reason: str` — причина остановки
- `agent_name: str` — имя агента

### Требование: Контракт AgentResult

Система ДОЛЖНА определять `AgentResult` как frozen dataclass с полями:
- `text: str`
- `tool_calls: list[ToolCall]`
- `usage: TokenUsage`
- `stop_reason: str` — "end_turn", "cancelled", "max_iterations", "tool_call"
- `agent_name: str`
- `error: str | None = None`

### Требование: Контракт ContextBroadcast

Система ДОЛЖНА определять `ContextBroadcast` как frozen dataclass с полями:
- `context: list[Message]`
- `available_agents: list[str]`
- `step: int`
- `correlation_id: str`
- `session_id: str`

### Требование: Контракт ChoreographyAnswer

Система ДОЛЖНА определять `ChoreographyAnswer` как frozen dataclass с полями:
- `agent_name: str`
- `action_taken: bool`
- `reasoning: str`
- `output: str | None`
- `status_signal: Literal["continue", "completed"]`
- `usage: TokenUsage`

### Требование: Базовый DomainEvent

Все контракты сообщений ДОЛЖНЫ наследоваться от базового класса `DomainEvent` для типобезопасной подписки.
