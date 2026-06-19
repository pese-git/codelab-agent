# Spec: session-aggregate

## ADDED Requirements

### Requirement: Aggregate Root Session

Система SHALL предоставлять `Session` как aggregate root, содержащий value objects:
- `id: SessionId` — уникальный идентификатор сессии
- `config: SessionConfig` — конфигурация сессии
- `history: ConversationHistory` — история сообщений
- `tool_calls: ToolCallRegistry` — реестр tool calls
- `permissions: PermissionState` — состояние разрешений
- `plan: AgentPlan` — план выполнения
- `multi_agent: MultiAgentState` — состояние multi-agent

#### Scenario: Создание Session aggregate root
- **WHEN** создается Session
- **THEN** объект содержит все value objects: config, history, tool_calls, permissions, plan, multi_agent

### Requirement: SessionConfig Value Object

Система SHALL предоставлять `SessionConfig` как frozen dataclass с полями:
- `cwd: str` — рабочая директория
- `config_values: dict[str, str]` — значения конфигурации (mode, model, etc.)
- `active_strategy: str` — активная стратегия выполнения
- `runtime_capabilities: ClientCapabilities` — возможности клиента

#### Scenario: Создание SessionConfig
- **WHEN** создается SessionConfig
- **THEN** объект содержит поля `cwd`, `config_values`, `active_strategy`, `runtime_capabilities`

### Requirement: ConversationHistory Value Object

Система SHALL предоставлять `ConversationHistory` с методами:
- `add(message: ConversationMessage)` — добавить сообщение
- `get_recent(n: int)` — получить последние N сообщений
- `get_messages()` — получить все сообщения

#### Scenario: Добавление сообщения в историю
- **WHEN** вызывается `add(message)`
- **THEN** сообщение добавляется в историю

#### Scenario: Получение последних сообщений
- **WHEN** вызывается `get_recent(n)`
- **THEN** возвращаются последние N сообщений

### Requirement: ToolCallRegistry Value Object

Система SHALL предоставлять `ToolCallRegistry` с методами:
- `create(tool_name: str, arguments: dict) -> ToolCall` — создать tool call
- `get(tool_call_id: str) -> ToolCall | None` — получить tool call
- `update(tool_call_id: str, result: ToolResult)` — обновить tool call
- `get_all()` — получить все tool calls

#### Scenario: Создание tool call
- **WHEN** вызывается `create(tool_name, arguments)`
- **THEN** создается новый ToolCall и добавляется в реестр

#### Scenario: Получение tool call
- **WHEN** вызывается `get(tool_call_id)`
- **THEN** возвращается ToolCall или None если не найден

### Requirement: PermissionState Value Object

Система SHALL предоставлять `PermissionState` с методами:
- `is_allowed(kind: str) -> bool` — проверить разрешение
- `set_policy(kind: str, policy: str)` — установить политику
- `cancel_request(request_id: JsonRpcId)` — отменить запрос
- `is_cancelled(request_id: JsonRpcId) -> bool` — проверить отмену

#### Scenario: Проверка разрешения
- **WHEN** вызывается `is_allowed(kind)`
- **THEN** возвращается bool в зависимости от политики

#### Scenario: Установка политики
- **WHEN** вызывается `set_policy(kind, policy)`
- **THEN** политика устанавливается для указанного kind

### Requirement: AgentPlan Value Object

Система SHALL предоставлять `AgentPlan` с методами:
- `add_step(step: PlanEntry)` — добавить шаг
- `update_step(index: int, status: PlanStatus)` — обновить статус шага
- `get_steps()` — получить все шаги

#### Scenario: Добавление шага в план
- **WHEN** вызывается `add_step(step)`
- **THEN** шаг добавляется в план

#### Scenario: Обновление статуса шага
- **WHEN** вызывается `update_step(index, status)`
- **THEN** статус шага обновляется

### Requirement: MultiAgentState Value Object

Система SHALL предоставлять `MultiAgentState` с полями:
- `active_strategy: str` — активная стратегия
- `active_agents: list[str]` — список активных агентов
- `parent_session_id: str | None` — ID родительской сессии
- `child_session_ids: list[str]` — ID дочерних сессий
- `is_child_session: bool` — флаг дочерней сессии

#### Scenario: Создание MultiAgentState
- **WHEN** создается MultiAgentState
- **THEN** объект содержит все поля для multi-agent состояния

### Requirement: Session Business Logic

`Session` SHALL инкапсулировать бизнес-логику:
- `add_message(message)` — добавить сообщение в историю
- `create_tool_call(tool_name, arguments)` — создать tool call
- `update_tool_call(tool_call_id, result)` — обновить tool call
- `set_permission_policy(kind, policy)` — установить политику разрешений

#### Scenario: Добавление сообщения через Session
- **WHEN** вызывается `session.add_message(message)`
- **THEN** сообщение добавляется в историю через value object

#### Scenario: Создание tool call через Session
- **WHEN** вызывается `session.create_tool_call(tool_name, arguments)`
- **THEN** tool call создается через ToolCallRegistry

### Requirement: SessionState ACP Protocol Model для сериализации

Система SHALL предоставлять `SessionState` как ACP Protocol Model для сериализации:
- Содержит только данные, не бизнес-логику
- Поддерживает миграцию schema_version
- Маппится в domain `Session` через `SessionMapper`

#### Scenario: SessionState для сериализации
- **WHEN** SessionState используется для сериализации
- **THEN** он содержит только данные без бизнес-логики

#### Scenario: Миграция schema_version
- **WHEN** загружается SessionState с старой версией
- **THEN** применяется миграция schema_version

### Requirement: SessionMapper

Система SHALL предоставлять `SessionMapper` с методами:
- `to_protocol(session: Session) -> SessionState` — конвертировать domain в protocol
- `to_domain(protocol: SessionState) -> Session` — конвертировать protocol в domain

#### Scenario: Конвертация domain в protocol
- **WHEN** вызывается `SessionMapper.to_protocol()` с Session
- **THEN** возвращается SessionState для сериализации

#### Scenario: Конвертация protocol в domain
- **WHEN** вызывается `SessionMapper.to_domain()` с SessionState
- **THEN** возвращается Session aggregate root
