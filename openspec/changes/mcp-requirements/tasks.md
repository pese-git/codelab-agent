## 1. HTTP Transport Implementation

- [ ] 1.1 Создать `HttpTransport` класс в `server/mcp/transport.py` с aiohttp.ClientSession
- [ ] 1.2 Реализовать `connect()`, `send_request()`, `disconnect()` методы
- [ ] 1.3 Добавить обработку HTTP headers из конфигурации
- [ ] 1.4 Обработка ошибок: connection refused, timeout, HTTP errors
- [ ] 1.5 Написать unit тесты для HttpTransport (mock aiohttp)
- [ ] 1.6 Написать integration тесты с mock MCP HTTP сервером

## 2. SSE Transport Implementation

- [ ] 2.1 Создать `SseTransport` класс в `server/mcp/transport.py`
- [ ] 2.2 Реализовать SSE event parsing (data:, event:, id: lines)
- [ ] 2.3 Реализовать `connect()`, `send_request()`, `disconnect()` методы
- [ ] 2.4 Добавить warning logging о deprecated status
- [ ] 2.5 Написать unit тесты для SseTransport
- [ ] 2.6 Написать integration тесты с mock MCP SSE сервером

## 3. MCP Server Config Update

- [ ] 3.1 Обновить `MCPServerConfig` модель: добавить `type`, `url`, `headers` поля
- [ ] 3.2 Добавить валидацию: stdio требует `command`, HTTP/SSE требует `url`
- [ ] 3.3 Обновить `get_env_dict()` → `get_connection_params()` method
- [ ] 3.4 Написать тесты для валидации конфигурации

## 4. MCPClient — Resources Support

- [ ] 4.1 Добавить `list_resources()` метод → `resources/list`
- [ ] 4.2 Добавить `read_resource(uri)` метод → `resources/read`
- [ ] 4.3 Создать модели: `MCPResource`, `MCPListResourcesResult`, `MCPReadResourceResult`
- [ ] 4.4 Кэширование ресурсов в `_resources_cache`
- [ ] 4.5 Написать unit тесты для resources methods
- [ ] 4.6 Написать integration тесты с mock MCP сервером (resources)

## 5. MCPClient — Prompts Support

- [ ] 5.1 Добавить `list_prompts()` метод → `prompts/list`
- [ ] 5.2 Добавить `get_prompt(name, arguments)` метод → `prompts/get`
- [ ] 5.3 Создать модели: `MCPPrompt`, `MCPListPromptsResult`, `MCPGetPromptResult`
- [ ] 5.4 Кэширование промптов в `_prompts_cache`
- [ ] 5.5 Написать unit тесты для prompts methods
- [ ] 5.6 Написать integration тесты с mock MCP сервером (prompts)

## 6. MCPClient — Notification Handling

- [ ] 6.1 Добавить `_notification_queue: asyncio.Queue` в MCPClient
- [ ] 6.2 Реализовать `_process_notifications()` background task
- [ ] 6.3 Добавить `register_handler(method, callback)` метод
- [ ] 6.4 Обработка `notifications/tools/list_changed` → refresh tools
- [ ] 6.5 Логирование всех notifications с DEBUG level
- [ ] 6.6 Написать unit тесты для notification handling

## 7. MCPManager — Auto-Reconnect

- [ ] 7.1 Добавить retry configuration: `max_retries`, `initial_delay`, `max_delay`, `backoff_multiplier`
- [ ] 7.2 Реализовать `reconnect_with_backoff()` с exponential backoff + jitter
- [ ] 7.3 Добавить `_state` tracking: READY, FAILED, RECONNECTING
- [ ] 7.4 Health check mechanism: periodic ping каждые 60s
- [ ] 7.5 Обработка FAILED state: graceful degradation, error reporting
- [ ] 7.6 Написать unit тесты для reconnect logic
- [ ] 7.7 Написать integration тесты с fault injection (kill subprocess)

## 8. Integration with ACP Protocol

- [ ] 8.1 Обновить `agentCapabilities.mcpCapabilities` в initialize response
- [ ] 8.2 Обновить `_initialize_mcp_servers()` для поддержки HTTP/SSE транспортов
- [ ] 8.3 Интеграция MCP resources с ACP ContentBlock types
- [ ] 8.4 Интеграция MCP prompts с session/prompt flow
- [ ] 8.5 Обновить `AgentOrchestrator._build_system_message()` для resources/prompts info
- [ ] 8.6 Написать integration тесты для полного MCP flow

## 9. Testing & Documentation

- [ ] 9.1 Создать mock MCP сервер с HTTP/SSE endpoints для тестов
- [ ] 9.2 Написать ~200+ тестов для всех новых функций
- [ ] 9.3 Обновить `doc/architecture/ACP_IMPLEMENTATION_VERIFICATION.md`
- [ ] 9.4 Добавить Mermaid диаграммы для новой архитектуры MCP
- [ ] 9.5 Запустить `make check` — все тесты должны проходить
- [ ] 9.6 Code review: ruff, ty, pytest coverage report
