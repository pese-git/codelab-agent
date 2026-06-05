# Tasks: Complete MCP Integration

## 1. Фаза 1 — MCP Tools в LLM Loop (P0)

### 1.1 MCPToolExecutor
- [x] 1.1.1 Создать `server/tools/executors/mcp_executor.py` — MCPToolExecutor класс
- [x] 1.1.2 Реализовать `execute(tool_name, arguments, session_state)` → ToolResult
- [x] 1.1.3 MCP content conversion: MCPTextContent → text, MCPImageContent → base64, MCPEmbeddedResource → embedded
- [x] 1.1.4 Timeout handling: configurable per-server timeout
- [x] 1.1.5 Error handling: MCP server crash, timeout, invalid response
- [x] 1.1.6 Тесты: execute success, execute timeout, execute error, content conversion

### 1.2 Интеграция в LLMLoopStage
- [x] 1.2.1 Добавить `mcp_manager` в `LLMLoopStage` constructor (через PromptOrchestrator)
- [x] 1.2.2 В `_process_tool_calls_for_llm_loop()` проверить: если `tool_name` начинается с `mcp:`, делегировать в MCPToolExecutor
- [x] 1.2.3 MCP tool calls создают `ToolCallState` с `kind="mcp"`
- [x] 1.2.4 Permission flow для MCP tools через `PermissionManager`
- [x] 1.2.5 Тесты: MCP tool call recognized, delegated, lifecycle complete

### 1.3 MCP Tools в AgentContext
- [x] 1.3.1 В `AgentOrchestrator._create_agent_context()` добавить MCP tools из `session_state.mcp_manager.get_all_tools()` в `available_tools`
- [x] 1.3.2 MCP tools проходят через `ToolMapping.acp_name_to_llm_name()` для совместимости имён
- [x] 1.3.3 Тесты: agent context содержит MCP tools, LLM получает их в tools list

### 1.4 Integration Tests — Фаза 1
- [x] 1.4.1 E2E тест: session/new → MCP connect → prompt → MCP tool call → response
- [x] 1.4.2 Integration тест: mock MCP server → tool call → LLM loop → result
- [x] 1.4.3 Integration тест: MCP tool permission flow (ask → allow → execute)

## 2. Фаза 2 — MCP Resources (P1)

### 2.1 Модели
- [x] 2.1.1 Создать `MCPResource` — uri, name, description, mimeType
- [x] 2.1.2 Создать `MCPResourceTemplate` — uriTemplate, name, description, mimeType
- [x] 2.1.3 Создать `MCPListResourcesResult`, [x] `MCPListResourceTemplatesResult`
- [x] 2.1.4 Создать `MCPReadResourceParams`, `MCPReadResourceResult`, [x] `MCPResourceContent` (typed union)
- [x] 2.1.5 Тесты: serialization, deserialization, validation

### 2.2 MCPClient Resources API
- [x] 2.2.1 `list_resources()` → MCPListResourcesResult
- [x] 2.2.2 `list_resource_templates()` → MCPListResourceTemplatesResult
- [x] 2.2.3 `read_resource(uri)` → MCPReadResourceResult
- [x] 2.2.4 Capability checking: server_capabilities.resources
- [x] 2.2.5 Тесты: list resources, read resource, capability check

### 2.3 MCPManager Resources
- [x] 2.3.1 `get_all_resources()` → list всех resources от всех серверов
- [x] 2.3.2 `read_resource(server_id, uri)` → читать resource с конкретного сервера
- [x] 2.3.3 Resource URI routing: по uri определить какой сервер обслуживает
- [x] 2.3.4 Тесты: get all resources, read resource, URI routing

### 2.4 ACP Integration
- [x] 2.4.1 MCP Resources → ACP ResourceLinkContent маппинг
- [x] 2.4.2 При session/load: MCP resources могут быть включены в replay
- [x] 2.4.3 Тесты: content conversion, replay integration

## 3. Фаза 3 — MCP Prompts (P1)

### 3.1 Модели
- [x] 3.1.1 Создать `MCPPrompt`, `MCPPromptArgument`
- [x] 3.1.2 Создать `MCPListPromptsResult`, `MCPGetPromptParams`, `MCPGetPromptResult`
- [x] 3.1.3 Создать `MCPPromptMessage` — role, content
- [x] 3.1.4 Тесты: serialization, deserialization, validation

### 3.2 MCPClient Prompts API
- [x] 3.2.1 `list_prompts()` → MCPListPromptsResult
- [x] 3.2.2 `get_prompt(name, arguments)` → MCPGetPromptResult
- [x] 3.2.3 Capability checking: server_capabilities.prompts
- [x] 3.2.4 Тесты: list prompts, get prompt, capability check

### 3.3 MCPManager Prompts
- [x] 3.3.1 `get_all_prompts()` → list всех prompts от всех серверов
- [x] 3.3.2 `get_prompt(server_id, name, arguments)` → получить prompt с аргументами
- [x] 3.3.3 Тесты: get all prompts, get prompt with arguments

### 3.4 ACP Integration
- [x] 3.4.1 MCP Prompts → ACP slash commands маппинг
- [x] 3.4.2 При вызове slash-команды: resolve MCP prompt → messages → inject в conversation
- [x] 3.4.3 Тесты: slash command integration, prompt resolution

## 4. Фаза 4 — Notifications и Auto-reconnect (P1)

### 4.1 Tool list change notifications
- [x] 4.1.1 В `_handle_message()` распознавать `notifications/tools/list_changed`
- [x] 4.1.2 Callback mechanism: MCPClient → MCPManager при изменении tools
- [x] 4.1.3 MCPManager → PromptOrchestrator → refresh available_tools
- [x] 4.1.4 Отправка `available_commands_update` notification клиенту
- [x] 4.1.5 Тесты: notification handling, tool refresh

### 4.2 Auto-reconnect
- [x] 4.2.1 MCPClient — health check (monitoring subprocess exit)
- [x] 4.2.2 MCPManager — reconnect policy: max_retries=5, exponential backoff
- [x] 4.2.3 При reconnect: re-initialize, re-list_tools, re-register
- [x] 4.2.4 Notification клиенту о disconnect/reconnect
- [x] 4.2.5 Graceful degradation: если server не восстанавливается, удалить из active
- [x] 4.2.6 Тесты: reconnect scenarios, max retries, backoff, graceful degradation

### 4.3 Resource/Prompt change notifications
- [x] 4.3.1 `notifications/resources/list_changed` handling
- [x] 4.3.2 `notifications/prompts/list_changed` handling
- [x] 4.3.3 Тесты: resource/prompt notification handling

## 5. Фаза 5 — Advanced Features (P2)

### 5.1 Image/Resource content в tool results
- [ ] 5.1.1 MCPImageContent → ACP ImageContent conversion
- [ ] 5.1.2 MCPEmbeddedResource → ACP EmbeddedContent conversion
- [ ] 5.1.3 Content pipeline: MCP content → ExtractedContent → LLM format
- [ ] 5.1.4 Тесты: image content, embedded resource content

### 5.2 MCP Roots
- [ ] 5.2.1 Создать `MCPRoot` — uri, name
- [ ] 5.2.2 `roots/list` handler в MCPClient
- [ ] 5.2.3 При initialize: отправить capabilities.roots
- [ ] 5.2.4 Roots из session.cwd → file://{cwd}
- [ ] 5.2.5 notifications/roots/list_changed при смене cwd
- [ ] 5.2.6 Тесты: roots listing, notification

### 5.3 MCP Sampling
- [ ] 5.3.1 Создать MCPSamplingMessage, sampling/createMessage handler
- [ ] 5.3.2 Делегирование в LLM провайдер → возврат completion
- [ ] 5.3.3 Model preferences mapping → LLM resolver
- [ ] 5.3.4 Тесты: sampling request → LLM → response

### 5.4 MCP Elicitation
- [ ] 5.4.1 Создать MCPElicitationRequest, elicitation/create handler
- [ ] 5.4.2 Делегирование в client → UI elicitation modal
- [ ] 5.4.3 Response validation against schema
- [ ] 5.4.4 Тесты: elicitation flow

### 5.5 Progress notifications
- [ ] 5.5.1 Progress token в request _meta.progressToken
- [ ] 5.5.2 notifications/progress handling
- [ ] 5.5.3 Progress → ACP notification (tool_call_update с progress)
- [ ] 5.5.4 Тесты: progress tracking

## 6. Фаза 6 — HTTP Transport (P2)

### 6.1 MCPHttpTransport
- [x] 6.1.1 Создать `server/mcp/transport.py` — HttpTransport (уже существует)
- [x] 6.1.2 POST для client→server messages
- [x] 6.1.3 SSE для server→client streaming (SseTransport)
- [x] 6.1.4 Headers: Authorization, Content-Type
- [x] 6.1.5 Connection pooling, retry logic
- [x] 6.1.6 Тесты: HTTP connect, request, response

### 6.2 MCPConfig HTTP support
- [x] 6.2.1 MCPServerConfig — type: "http"|"sse"|"stdio", url, headers (уже в модели)
- [x] 6.2.2 Подключить HTTP/SSE transport в MCPClient.connect()
- [x] 6.2.3 mcpCapabilities через конфигурацию ACPProtocol (mcp_http_enabled, mcp_sse_enabled)
- [x] 6.2.4 Тесты: HTTP server config, connection

## 7. Documentation

- [ ] 7.1 Обновить `openspec/specs/codelab.md` — раздел 19 (MCP интеграция)
- [ ] 7.2 Обновить `doc/architecture/ACP_IMPLEMENTATION_VERIFICATION.md` — новый статус
- [ ] 7.3 Обновить `doc/architecture/MCP_IMPLEMENTATION_PLAN.md` — отметить выполненные задачи
