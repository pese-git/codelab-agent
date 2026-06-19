# Spec: session-aggregate

## ДОБАВЛЕННЫЕ Требования

### Требование: Aggregate Root Session

Система ДОЛЖНА предоставлять `Session` как aggregate root, содержащий value objects:
- `id: SessionId` — уникальный идентификатор сессии
- `config: SessionConfig` — конфигурация сессии
- `history: ConversationHistory` — история сообщений
- `tool_calls: ToolCallRegistry` — реестр tool calls
- `permissions: PermissionState` — состояние разрешений
- `plan: AgentPlan` — план выполнения
- `multi_agent: MultiAgentState` — состояние multi-agent

### Требование: SessionConfig Value Object

Система ДОЛЖНА предоставлять `SessionConfig` как frozen dataclass с полями:
- `cwd: str` — рабочая директория
- `config_values: dict[str, str]` — значения конфигурации (mode, model, etc.)
- `active_strategy: str` — активная стратегия выполнения
- `runtime_capabilities: ClientCapabilities` — возможности клиента

### Требование: ConversationHistory Value Object

Система ДОЛЖНА предоставлять `ConversationHistory` с методами:
- `add(message: ConversationMessage)` — добавить сообщение
- `get_recent(n: int)` — получить последние N сообщений
- `get_messages()` — получить все сообщения

### Требование: ToolCallRegistry Value Object

Система ДОЛЖНА предоставлять `ToolCallRegistry` с методами:
- `create(tool_name: str, arguments: dict) -> ToolCall` — создать tool call
- `get(tool_call_id: str) -> ToolCall | None` — получить tool call
- `update(tool_call_id: str, result: ToolResult)` — обновить tool call
- `get_all()` — получить все tool calls

### Требование: PermissionState Value Object

Система ДОЛЖНА предоставлять `PermissionState` с методами:
- `is_allowed(kind: str) -> bool` — проверить разрешение
- `set_policy(kind: str, policy: str)` — установить политику
- `cancel_request(request_id: JsonRpcId)` — отменить запрос
- `is_cancelled(request_id: JsonRpcId) -> bool` — проверить отмену

### Требование: AgentPlan Value Object

Система ДОЛЖНА предоставлять `AgentPlan` с методами:
- `add_step(step: PlanEntry)` — добавить шаг
- `update_step(index: int, status: PlanStatus)` — обновить статус шага
- `get_steps()` — получить все шаги

### Требование: MultiAgentState Value Object

Система ДОЛЖНА предоставлять `MultiAgentState` с полями:
- `active_strategy: str` — активная стратегия
- `active_agents: list[str]` — список активных агентов
- `parent_session_id: str | None` — ID родительской сессии
- `child_session_ids: list[str]` — ID дочерних сессий
- `is_child_session: bool` — флаг дочерней сессии

### Требование: Session Business Logic

`Session` ДОЛЖЕН инкапсулировать бизнес-логику:
- `add_message(message)` — добавить сообщение в историю
- `create_tool_call(tool_name, arguments)` — создать tool call
- `update_tool_call(tool_call_id, result)` — обновить tool call
- `set_permission_policy(kind, policy)` — установить политику разрешений

### Требование: SessionState ACP Protocol Model для сериализации

Система ДОЛЖНА предоставлять `SessionState` как ACP Protocol Model для сериализации:
- Содержит только данные, не бизнес-логику
- Поддерживает миграцию schema_version
- Маппится в domain `Session` через `SessionMapper`

### Требование: SessionMapper

Система ДОЛЖНА предоставлять `SessionMapper` с методами:
- `to_protocol(session: Session) -> SessionState` — конвертировать domain в protocol
- `to_domain(protocol: SessionState) -> Session` — конвертировать protocol в domain
