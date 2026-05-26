# Proposal: Multi-Provider LLM Architecture

## Why

Текущая реализация поддерживает только один LLM-провайдер — OpenAI (и Mock для тестов). Это ограничивает применимость CodeLab в production: нет поддержки Anthropic Claude, локальных моделей (Ollama, LMStudio), агрегаторов (OpenRouter), а также стратегических сервисов OpenCode Zen и Go. Кроме того, отсутствует механизм переключения моделей во время сессии через ACP `configOptions`, fallback при ошибках провайдера и расширяемая архитектура для добавления новых провайдеров.

## What Changes

- **Новая система регистрации провайдеров** — `LLMProviderRegistry` с динамической регистрацией и factory-паттерном вместо hardcoded if/else в DI
- **Базовый класс `OpenAICompatibleProvider`** — для всех провайдеров с OpenAI-compatible API (OpenRouter, Zen, Go, Ollama, LMStudio, xAI, DeepSeek)
- **Новые провайдеры**: Anthropic, OpenRouter, Zen, Go, Ollama, LMStudio
- **Единый configOption `model`** с форматом `"provider/model"` (например, `"anthropic/claude-sonnet-4"`) — клиент переключает модель через `session/set_config_option`
- **Fallback-цепочка провайдеров** — pluggable через `FallbackStrategy` интерфейс (MVP: Sequential, extension points для Cost, Latency, Smart)
- **Model Discovery** — pluggable через `ModelDiscovery` интерфейс (MVP: Static, extension для dynamic Ollama/LMStudio)
- **Telemetry** — pluggable через `TelemetrySink` интерфейс (MVP: NoOp, extension для Prometheus, etc.)
- **ProviderEventBus** — система событий провайдеров (models_updated, provider_failed, fallback_triggered)
- **BREAKING**: `LLMConfig` расширяется — добавляется `providers: dict[str, ProviderConfig]` и `fallback: FallbackConfig`
- **BREAKING**: `LLMProvider.initialize()` принимает `LLMConfig` вместо `dict[str, Any]`

## Capabilities

### New Capabilities
- `multi-provider-llm`: Регистрация, конфигурация и переключение между несколькими LLM-провайдерами и моделями через ACP configOptions
- `llm-fallback`: Автоматический fallback между провайдерами при ошибках с pluggable стратегией
- `model-discovery`: Динамическое обнаружение доступных моделей для локальных провайдеров (Ollama, LMStudio)
- `provider-telemetry`: Сбор метрик производительности и стоимости провайдеров (extension point)

### Modified Capabilities
- `codelab`: Раздел 20 (LLM Провайдеры) — заменяется новой архитектурой с Registry, Strategies, Discovery

## Impact

**Затронутые файлы сервера:**
- `server/llm/` — полный рефакторинг: новые модули `registry.py`, `resolver.py`, `models.py`, `fallback/`, `discovery/`, `telemetry/`, `events.py`, `errors.py`, `providers/`
- `server/config.py` — расширение `LLMConfig` (provider → providers dict, fallback config)
- `server/di.py` — `LLMProvider_` заменяется на Registry-based factory
- `server/agent/orchestrator.py` — получает `ModelResolver` вместо прямого `LLMProvider`
- `server/protocol/handlers/config.py` — генерация configOptions из Registry
- `server/protocol/handlers/pipeline/stages/llm_loop.py` — использование resolver для получения провайдера
- `server/cli.py` — новые CLI аргументы для fallback конфигурации

**Затронутые зависимости:**
- `anthropic` — перемещается из optional-dependencies в основные
- Новые: `httpx` (для Ollama/LMStudio discovery, если понадобится)

**Тесты:**
- ~200+ новых тестов для Registry, Resolver, Fallback, Discovery, каждого нового провайдера
- Обновление существующих тестов `test_llm_provider.py`

**ACP Protocol:**
- Полная совместимость — используется стандартный `configOptions` с `category: "model"` и `session/set_config_option`
