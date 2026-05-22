# Tasks: Multi-Provider LLM Architecture

## 1. Foundation — Models и Interfaces

- [ ] 1.1 Создать `server/llm/models.py` — CompletionRequest, CompletionResponse, LLMMessage, LLMToolCall, ModelInfo, ProviderInfo, StopReason enum
- [ ] 1.2 Создать `server/llm/errors.py` — ProviderError, ProviderNotFoundError, ModelNotFoundError, AllProvidersFailed, ProviderErrorType enum
- [ ] 1.3 Обновить `server/llm/base.py` — обновить LLMProvider ABC: `initialize(config: LLMConfig)`, `name` property, `capabilities` property
- [ ] 1.4 Создать `server/llm/events.py` — ProviderEventBus, ProviderInitialized, ProviderFailed, ModelsUpdated, FallbackTriggered events
- [ ] 1.5 Тесты для models.py — сериализация, валидация, enum values
- [ ] 1.6 Тесты для errors.py — иерархия исключений, error types

## 2. Registry и Resolver

- [ ] 2.1 Создать `server/llm/registry.py` — LLMProviderRegistry с register(), create_provider(), list_all_models(), get_provider_info(), get_model_info()
- [ ] 2.2 Создать `server/llm/resolver.py` — ModelRef.parse(), ModelResolver.resolve()
- [ ] 2.3 Тесты для registry.py — регистрация, создание, листинг, ошибки
- [ ] 2.4 Тесты для resolver.py — парсинг "provider/model", разрешение в провайдер, ошибки

## 3. Fallback System

- [ ] 3.1 Создать `server/llm/fallback/base.py` — FallbackStrategy ABC, FallbackContext
- [ ] 3.2 Создать `server/llm/fallback/sequential.py` — SequentialFallback реализация
- [ ] 3.3 Создать `server/llm/fallback/circuit_breaker.py` — CircuitBreaker (extension point)
- [ ] 3.4 Создать `server/llm/fallback/config.py` — FallbackConfig dataclass
- [ ] 3.5 Создать `server/llm/fallback/factory.py` — FallbackStrategyFactory
- [ ] 3.6 Создать `server/llm/fallback/orchestrator.py` — FallbackOrchestrator
- [ ] 3.7 Тесты для SequentialFallback — порядок, circuit open, all failed
- [ ] 3.8 Тесты для CircuitBreaker — failure threshold, open/closed states, reset
- [ ] 3.9 Тесты для FallbackOrchestrator — success first, fallback, non-retryable error, all failed

## 4. Discovery System

- [ ] 4.1 Создать `server/llm/discovery/base.py` — ModelDiscovery ABC
- [ ] 4.2 Создать `server/llm/discovery/static.py` — StaticDiscovery
- [ ] 4.3 Создать `server/llm/discovery/config.py` — DiscoveryConfig
- [ ] 4.4 Тесты для StaticDiscovery — static list, empty list
- [ ] 4.5 Тесты для ModelDiscovery ABC — interface compliance

## 5. Telemetry System

- [ ] 5.1 Создать `server/llm/telemetry/base.py` — TelemetrySink ABC
- [ ] 5.2 Создать `server/llm/telemetry/noop.py` — NoOpTelemetry
- [ ] 5.3 Тесты для NoOpTelemetry — silent pass-through

## 6. OpenAI-Compatible Provider Base

- [ ] 6.1 Создать `server/llm/providers/openai_compatible.py` — OpenAICompatibleProvider базовый класс с _convert_to_openai_format(), _parse_completion(), _validate_message_history()
- [ ] 6.2 Рефакторинг `server/llm/providers/openai.py` — OpenAIProvider наследуется от OpenAICompatibleProvider
- [ ] 6.3 Тесты для OpenAICompatibleProvider — conversion, parsing, validation
- [ ] 6.4 Тесты для OpenAIProvider — backward compatibility, completion, streaming

## 7. Anthropic Provider

- [ ] 7.1 Создать `server/llm/providers/anthropic.py` — AnthropicProvider с Messages API, tool format conversion, stop reason mapping
- [ ] 7.2 Добавить `anthropic` в основные dependencies pyproject.toml
- [ ] 7.3 Тесты для AnthropicProvider — completion, tools, stop reasons, error handling

## 8. OpenAI-Compatible Derivatives

- [ ] 8.1 Создать `server/llm/providers/openrouter.py` — OpenRouterProvider (base_url="https://openrouter.ai/api/v1")
- [ ] 8.2 Создать `server/llm/providers/zen.py` — ZenProvider (base_url="https://zen.opencode.ai/v1")
- [ ] 8.3 Создать `server/llm/providers/go.py` — GoProvider (base_url="https://go.opencode.ai/v1")
- [ ] 8.4 Создать `server/llm/providers/ollama.py` — OllamaProvider (base_url="http://localhost:11434/v1", default models)
- [ ] 8.5 Создать `server/llm/providers/lmstudio.py` — LMStudioProvider (base_url="http://localhost:1234/v1", default models)
- [ ] 8.6 Тесты для каждого derivative provider — initialization, base_url, default model

## 9. Mock Provider Update

- [ ] 9.1 Обновить `server/llm/providers/mock.py` — использовать новые модели (LLMConfig вместо dict)
- [ ] 9.2 Обновить тесты mock provider — compatibility с новым интерфейсом

## 10. Configuration Update

- [ ] 10.1 Обновить `server/config.py` — расширить LLMConfig: providers dict, FallbackConfig, ProviderConfig
- [ ] 10.2 Обновить env vars — CODELAB_LLM_PROVIDERS, CODELAB_FALLBACK_* 
- [ ] 10.3 Тесты для новой конфигурации — parsing, defaults, validation

## 11. DI Container Update

- [ ] 11.1 Обновить `server/di.py` — LLMProvider_ заменяется на Registry-based factory
- [ ] 11.2 Обновить AgentProvider — AgentOrchestrator получает ModelResolver вместо LLMProvider
- [ ] 11.3 Зарегистрировать все провайдеры в Registry при инициализации
- [ ] 11.4 Тесты для DI — registry creation, provider resolution, orchestrator wiring

## 12. ConfigOptions и Model Switching

- [ ] 12.1 Создать `server/protocol/handlers/config_option_builder.py` — ConfigOptionBuilder.build_model_config_option()
- [ ] 12.2 Обновить `server/protocol/handlers/session.py` — генерация configOptions из Registry
- [ ] 12.3 Обновить `server/protocol/handlers/config.py` — handle_set_config_option для configId="model"
- [ ] 12.4 Тесты для configOption builder — model list generation, pricing description
- [ ] 12.5 Тесты для model switching — set_config_option, notification, invalid value

## 13. Orchestrator Integration

- [ ] 13.1 Обновить `server/agent/orchestrator.py` — использовать ModelResolver для получения провайдера из session config
- [ ] 13.2 Обновить `server/protocol/handlers/pipeline/stages/llm_loop.py` — resolver вместо прямого provider
- [ ] 13.3 Тесты для orchestrator — model resolution per session, fallback integration

## 14. CLI Update

- [ ] 14.1 Обновить `server/cli.py` — новые аргументы: --fallback-enabled, --fallback-strategy, --fallback-order
- [ ] 14.2 Тесты для CLI — argument parsing, config overrides

## 15. Provider Event Bus Integration

- [ ] 15.1 Интегрировать ProviderEventBus в provider initialization flow
- [ ] 15.2 Интегрировать ProviderEventBus в request/response flow
- [ ] 15.3 Тесты для event bus — event emission, logging

## 16. Module Exports

- [ ] 16.1 Обновить `server/llm/__init__.py` — экспорты всех новых модулей
- [ ] 16.2 Обновить `server/llm/providers/__init__.py` — экспорты всех провайдеров

## 17. Integration Tests

- [ ] 17.1 E2E тест: full flow — initialize → session/new → configOptions → set_config_option(model) → prompt
- [ ] 17.2 E2E тест: fallback chain — primary fails → fallback succeeds
- [ ] 17.3 E2E тест: model switching mid-session
- [ ] 17.4 Интеграционный тест: Registry → Resolver → Provider → Response

## 18. Documentation

- [ ] 18.1 Обновить `openspec/specs/codelab.md` — раздел 20 (LLM Провайдеры)
- [ ] 18.2 Обновить `doc/architecture/ACP_IMPLEMENTATION_VERIFICATION.md` — новый статус
- [ ] 18.3 Обновить README — новые провайдеры, конфигурация, fallback

## 19. TOML Configuration System

- [ ] 19.1 Создать загрузчик TOML: `codelab.toml` → `LLMConfig` через `tomllib`
- [ ] 19.2 Реализовать merge logic: `~/.codelab/auth.toml` → `codelab.toml` → `codelab.local.toml` → `.env` → CLI
- [ ] 19.3 Добавить поддержку per-model конфигурации (`ModelConfig` с `context_window`, `max_output_tokens`, `cost_*`)
- [ ] 19.4 Добавить CLI аргумент `--config` для custom пути к TOML-файлу
- [ ] 19.5 Тесты для TOML loader — парсинг, merge, per-model config, missing files
- [ ] 19.6 Добавить `codelab.toml.example` в репозиторий как шаблон

## 21. Cleanup

- [ ] 21.1 Удалить старый `openai_provider.py` (заменён на providers/openai.py)
- [ ] 21.2 Удалить старый `mock_provider.py` (заменён на providers/mock.py)
- [ ] 21.3 Запустить `make check` — lint, typecheck, все тесты
