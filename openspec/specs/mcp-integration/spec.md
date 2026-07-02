# Spec: MCP Integration

## MCP Tools в LLM Loop

Система **MUST** подключать MCP инструменты к LLM loop, позволяя LLM обнаруживать и вызывать инструменты от MCP серверов.

### Tool Discovery

- Система **MUST** добавлять MCP инструменты из `MCPManager.get_all_tools()` в `AgentContext.available_tools`
- MCP инструменты **MUST** использовать namespace формат `mcp:{server_id}:{tool_name}`
- MCP инструменты **MUST** проходить через `ToolMapping.acp_name_to_llm_name()` для совместимости с LLM API
- LLM **MUST** получать MCP инструменты в том же формате что и встроенные инструменты

### Tool Execution

- При tool call с именем начинающимся с `mcp:`, система **MUST** делегировать выполнение в `MCPManager.call_tool()`
- MCP tool calls **MUST** создавать `ToolCallState` с inferred kind (read, edit, delete, move, search, execute, think, fetch, switch_mode, other) через `MCPToolAdapter._infer_kind()`
- MCP tool calls **MUST** проходить полный lifecycle: pending → in_progress → completed/failed
- MCP tool calls **MUST** проходить через `PermissionManager` (allow/deny/ask chain)
- Timeout для MCP tool calls **MUST** быть настраиваемым per-server
- При ошибке MCP сервера, tool call **MUST** переходить в статус `failed` с описанием ошибки

### Content Conversion

- MCP tool result content **MUST** конвертироваться в ACP content format:
  - `MCPTextContent.type == "text"` → `TextContent`
  - `MCPImageContent.type == "image"` → `ImageContent` (base64, media_type preserved)
  - `MCPEmbeddedResource.type == "resource"` → `EmbeddedContent`
- Конвертированный контент **MUST** передаваться в LLM как tool result

## MCP Resources

Система **MUST** поддерживать MCP Resources — пассивные data sources для контекста.

### Resource Discovery

- MCPClient **MUST** вызывать `resources/list` при инициализации если server declares `capabilities.resources`
- MCPClient **MUST** вызывать `resources/templates/list` если server declares resource templates
- MCPManager **MUST** агрегировать resources от всех подключённых серверов

### Resource Reading

- MCPClient **MUST** поддерживать `read_resource(uri)` → `MCPReadResourceResult`
- MCPManager **MUST** маршрутизировать `read_resource` к правильному серверу по URI
- Resource content **MUST** конвертироваться в ACP `ResourceLinkContent`

### Resource Models

- `MCPResource`: uri (str), name (str), description (str), mimeType (str)
- `MCPResourceTemplate`: uriTemplate (str), name (str), description (str), mimeType (str)
- `MCPResourceContent`: uri (str), mimeType (str), text (str?), blob (str?)

## MCP Prompts

Система **MUST** поддерживать MCP Prompts — параметризованные prompt templates.

### Prompt Discovery

- MCPClient **MUST** вызывать `prompts/list` при инициализации если server declares `capabilities.prompts`
- MCPManager **MUST** агрегировать prompts от всех подключённых серверов

### Prompt Resolution

- MCPClient **MUST** поддерживать `get_prompt(name, arguments)` → `MCPGetPromptResult`
- MCP prompts **MUST** маппиться на ACP slash commands
- При вызове slash-команды, система **MUST** resolve MCP prompt → messages → inject в conversation

### Prompt Models

- `MCPPrompt`: name (str), description (str), arguments (list[MCPPromptArgument])
- `MCPPromptArgument`: name (str), description (str), required (bool), enum (list[str]?)
- `MCPPromptMessage`: role (str), content (MCPContent)

## MCP Notifications

Система **MUST** обрабатывать MCP notifications от серверов.

### Tool List Changed

- При получении `notifications/tools/list_changed`, система **MUST**:
  1. Вызвать `tools/list` для получения обновлённого списка
  2. Обновить кэш инструментов в MCPManager
  3. Обновить `available_tools` в active session
  4. Отправить `available_commands_update` notification клиенту

### Resource/Prompt List Changed

- При получении `notifications/resources/list_changed`, система **MUST** refresh resources
- При получении `notifications/prompts/list_changed`, система **MUST** refresh prompts

## MCP Auto-reconnect

Система **MUST** автоматически переподключаться к MCP серверам при падении.

### Reconnect Policy

- Max retries: **5** попыток
- Backoff: exponential, starting at 1s, max 16s
- Health check: monitoring subprocess exit code
- При успешном reconnect: re-initialize, re-list_tools, re-register

### Graceful Degradation

- Если server не восстанавливается после max retries, система **MUST**:
  1. Удалить сервер из active servers
  2. Отправить notification клиенту о disconnect
  3. Удалить MCP инструменты этого сервера из available_tools

## MCP Roots

Система **MUST** поддерживать MCP Roots — filesystem boundaries.

### Root Management

- При session creation, система **MUST** отправить roots: `[{uri: "file://{cwd}", name: "workspace"}]`
- При смене cwd, система **MUST** отправить `notifications/roots/list_changed`
- MCPClient **MUST** поддерживать `roots/list` handler

## MCP HTTP Transport

Система **MUST** поддерживать HTTP transport для remote MCP servers.

### Transport Requirements

- POST для client→server messages
- SSE для server→client streaming (optional)
- Headers: Authorization, Content-Type из MCPServerConfig
- Connection pooling, retry logic

### Configuration

- `MCPServerConfig` **MUST** поддерживать `type: "http" | "sse" | "stdio"`
- HTTP config: `type`, `url`, `headers`
- При HTTP transport, `mcpCapabilities.http` **MUST** быть `true` в initialize response

## MCP Tool Execution Resilience

Система **MUST** обеспечивать устойчивость выполнения MCP инструментов через decorator chain.

### MCP Exceptions Hierarchy

Система **MUST** предоставлять специализированные исключения:

- `MCPError` — базовое исключение для MCP (наследует `ToolExecutionError`)
- `MCPTimeoutError` — timeout при вызове инструмента (содержит `tool_name`, `timeout`)
- `MCPConnectionError` — ошибка соединения с сервером
- `MCPValidationError` — ошибка валидации аргументов
- `MCPServerError` — ошибка на стороне MCP сервера

### Timeout

Система **MUST** ограничивать время выполнения MCP инструментов:

- Timeout **MUST** быть настраиваемым per-server (default: 30s)
- При превышении timeout **MUST** генерироваться `MCPTimeoutError`
- Timeout **MUST** реализовываться через `asyncio.wait_for()`
- MCPToolExecutor **MUST** оборачиваться в `TimeoutDecorator`

### Retry

Система **MUST** автоматически повторять вызовы при временных ошибках:

- Retry **MUST** применяться только к retryable ошибкам: `MCPTimeoutError`, `MCPConnectionError`
- Non-retryable ошибки (`MCPValidationError`, `MCPServerError`) **MUST** возвращаться сразу
- Retry **MUST** использовать exponential backoff: `delay = backoff_factor ^ attempt`
- Default: `max_retries = 3`, `backoff_factor = 2.0` (delays: 1s → 2s → 4s)
- MCPToolExecutor **MUST** оборачиваться в `RetryDecorator`

### Fallback

Система **SHOULD** поддерживать fallback на альтернативный MCP сервер:

- `MCPServerConfig` **SHOULD** поддерживать опциональный `fallback: MCPServerConfig`
- При ошибке primary сервера после всех retry **SHOULD** переключаться на fallback
- Fallback сервер **MUST** предоставлять те же инструменты (валидация при конфигурации)
- Переключение **MUST** логироваться с указанием причины
- Fallback **MUST** реализовываться через `FallbackStrategy` (Strategy Pattern)

### Decorator Chain

MCPToolExecutor **MUST** использовать chain of decorators:

```
Base Executor → Timeout → Retry → Metrics → Tracing
```

- Каждый декоратор **MUST** реализовывать `ToolExecutorDecorator` (абстрактный базовый класс)
- Декораторы **MUST** добавлять одну ответственность (Single Responsibility Principle)
- Порядок декораторов **MUST** быть: Timeout → Retry → Metrics → Tracing

### Health Check

Система **SHOULD** периодически проверять доступность MCP серверов:

- `MCPHealthCheckService` **SHOULD** проверять серверы каждые 30s
- Health check **SHOULD** использовать `client.ping()` с timeout 5s
- При изменении статуса **MUST** уведомлять зарегистрированные callbacks (Observer Pattern)
- Health check **SHOULD** запускаться как background task

### Observability

Система **MUST** собирать метрики выполнения MCP инструментов:

- Latency (per tool, per server)
- Success rate (per tool, per server)
- Error count (per error type)
- Retry count (per tool)
- Fallback usage count

Tracing **MUST** интегрироваться с существующим `Tracer`:

- Каждый MCP tool call **MUST** создавать span `mcp_tool_execution`
- Span **MUST** содержать атрибуты: `tool_name`, `server_id`, `success`, `error`
- Span **MUST** быть частью span hierarchy (parent = `agent_loop`)
