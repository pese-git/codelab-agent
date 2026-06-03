# Design: Multi-Provider LLM Architecture

## Context

**Текущее состояние:** CodeLab использует единственный LLM-провайдер — `OpenAIProvider`. Провайдер создаётся в DI-контейнере через hardcoded if/else в `di.py:LLMProvider_`. Конфигурация — плоская `LLMConfig` с полями `provider`, `model`, `api_key`, `base_url`. Переключение модели требует перезапуска сервера.

**Проблемы:**
1. Нет поддержки Anthropic, Ollama, OpenRouter, Zen, Go
2. Нельзя переключить модель во время сессии
3. Нет fallback при ошибках провайдера
4. Добавление нового провайдера требует изменения `di.py`
5. `LLMProvider.initialize()` принимает `dict[str, Any]` — нет типизации конфигурации
6. Все OpenAI-compatible провайдеры дублируют код `OpenAIProvider`

**Ограничения:**
- ACP protocol не определяет provider-specific методы — используем стандартный `configOptions`
- Клиент не знает о провайдерах — видит только список моделей в `configOptions`
- Сервер должен работать с одним активным провайдером на сессию

## Goals / Non-Goals

**Goals:**
- Поддержка 7+ провайдеров: OpenAI, Anthropic, OpenRouter, Zen, Go, Ollama, LMStudio
- Переключение модели во время сессии через `session/set_config_option` с форматом `"provider/model"`
- Fallback-цепочка при ошибках провайдера (MVP: Sequential)
- Расширяемая архитектура — новый провайдер = один файл + регистрация
- Extension points для future: CircuitBreaker, CostFallback, SmartFallback, dynamic model discovery, telemetry

**Non-Goals:**
- Не делаем dynamic model discovery для Ollama/LMStudio в MVP (static defaults)
- Не делаем CircuitBreaker в MVP (extension point заложён)
- Не делаем Cost/Latency/Smart fallback в MVP (extension point заложён)
- Не делаем telemetry collection в MVP (extension point заложён)
- Не меняем ACP protocol — используем существующие `configOptions`

## Decisions

### 1. Registry Pattern для провайдеров

**Решение:** `LLMProviderRegistry` — singleton с методами `register()`, `get_provider()`, `list_all_models()`.

**Почему:** Убирает if/else из DI. Новый провайдер = вызов `register()` при старте. Registry хранит factory-функции, создаёт провайдеры лениво.

**Альтернативы:**
- DI auto-discovery — слишком магический, сложно тестировать
- Конфигурационный файл — лишняя сложность для MVP

### 2. `OpenAICompatibleProvider` как базовый класс

**Решение:** Все OpenAI-compatible провайдеры наследуются от `OpenAICompatibleProvider`, который содержит всю логику работы с OpenAI SDK. Различия — только `base_url` и `default_model`.

```
OpenAIProvider        → OpenAICompatibleProvider (base_url=None, default_model="gpt-4o")
OpenRouterProvider    → OpenAICompatibleProvider (base_url="https://openrouter.ai/api/v1")
ZenProvider           → OpenAICompatibleProvider (base_url="https://zen.opencode.ai/v1")
GoProvider            → OpenAICompatibleProvider (base_url="https://go.opencode.ai/v1")
OllamaProvider        → OpenAICompatibleProvider (base_url="http://localhost:11434/v1")
LMStudioProvider      → OpenAICompatibleProvider (base_url="http://localhost:1234/v1")
```

**Почему:** 90% кода `OpenAIProvider` — универсальная логика. Наследование устраняет дублирование.

**Альтернативы:**
- Composition — больше boilerplate, не нужно для такого случая
- LiteLLM wrapper — 50+ sub-dependencies, overkill

### 3. Anthropic — отдельная реализация

**Решение:** `AnthropicProvider` не наследуется от `OpenAICompatibleProvider` — использует `anthropic` SDK с Messages API.

**Почему:** Anthropic API fundamentally отличается:
- Messages API вместо Chat Completions
- `max_tokens` обязателен в запросе
- Tool format: `input_schema` вместо `parameters`
- Prompt caching (`cache_control`)
- Extended thinking (Claude 3.7+)

### 4. Формат модели: `"provider/model"`

**Решение:** ConfigOption `model` использует value формата `"openai/gpt-4o"`, `"anthropic/claude-sonnet-4"`, `"ollama/llama3.1:70b"`.

**Почему:** Один configOption вместо двух (`provider` + `model`). Клиент видит один селектор. Сервер парсит provider и model из одной строки.

**Парсинг:** `ModelRef.parse("openai/gpt-4o")` → `ModelRef(provider_id="openai", model_id="gpt-4o")`

### 5. Fallback — Strategy Pattern

**Решение:** `FallbackStrategy` (ABC) с реализацией `SequentialFallback` для MVP. Extension points через интерфейс:

```python
class FallbackStrategy(ABC):
    async def select_provider(candidates, request, context) -> LLMProvider
    def on_success(self, provider_id: str)
    def on_failure(self, provider_id: str, error: ProviderError)
```

**Почему:** Strategy Pattern позволяет добавить CircuitBreaker, CostFallback, SmartFallback без изменения core кода.

**Конфигурация:**
```python
fallback:
  enabled: false
  strategy: "sequential"  # sequential | cost | latency | smart
  order: ["openai", "openrouter", "ollama"]
  retry_on: ["rate_limit", "timeout"]
```

### 6. Model Discovery — Static для MVP

**Решение:** Все провайдеры используют `StaticDiscovery` — модели захардкожены в коде. Для Ollama/LMStudio — список популярных моделей по умолчанию.

**Почему:** Ollama может быть не запущен при старте сервера. Static discovery = сервер стартует мгновенно. Dynamic discovery — future extension через `ModelDiscovery` интерфейс.

### 7. Telemetry — NoOp для MVP

**Решение:** `TelemetrySink` (ABC) с `NoOpTelemetry` по умолчанию. Extension point для Prometheus, Datadog, etc.

**Интерфейс:**
```python
class TelemetrySink(ABC):
    async def record_request(provider, model, latency_ms, success)
    async def record_cost(provider, model, cost_usd)
```

### 8. ProviderEventBus — для уведомлений

**Решение:** Простой event bus для provider-событий. В MVP — только логирует. В future — можно добавить WebSocket notifications клиенту об изменении доступных моделей.

**События:** `ProviderInitialized`, `ProviderFailed`, `ModelsUpdated`, `FallbackTriggered`

### 9. TOML как основной формат конфигурации

**Решение:** Использовать TOML-файлы как основной формат конфигурации, аналогично `opencode.json` в OpenCode. Три уровня конфигурации с приоритетом:

```
CLI args > .env > codelab.local.toml > codelab.toml > ~/.codelab/auth.toml > defaults
```

- `codelab.toml` — проект (коммитится в git), содержит структуру провайдеров и моделей
- `codelab.local.toml` — project-level override (в `.gitignore`), содержит project-specific секреты
- `~/.codelab/auth.toml` — глобальный файл аутентификации, содержит API keys общие для всех проектов

Модели определяются как TOML map:
```toml
[llm.providers.openai.models]
gpt-4o = {}
o3 = { context_window = 200000, max_output_tokens = 16384 }
```

**Почему:** TOML читаемый, встроен в Python 3.11+ (`tomllib`), поддерживает вложенные структуры без зависимостей. Формат моделей как map повторяет подход OpenCode.

**Альтернативы:**
- JSON — нет комментариев, скобки менее читаемы
- YAML — нужна `pyyaml` dependency
- Только `.env` — не подходит для вложенных структур

### 10. Конфигурация — расширение `LLMConfig`

**Решение:**
```python
class LLMConfig(BaseModel):
    provider: str = "openai"           # активный провайдер
    model: str = "gpt-4o"              # активная модель
    providers: dict[str, ProviderConfig]  # конфиг всех провайдеров
    fallback: FallbackConfig           # fallback настройки
    temperature: float = 0.7
    max_tokens: int = 8192
```

**Почему:** Обратная совместимость — `provider` и `model` остаются. Новые поля — optional с defaults.

### 10. DI — Registry-based factory

**Решение:** `LLMProvider_` в DI создаёт Registry, регистрирует все провайдеры, возвращает Registry как зависимость. `AgentOrchestrator` получает `ModelResolver` вместо прямого `LLMProvider`.

**Почему:** `AgentOrchestrator` должен резолвить модель из session config, а не использовать один глобальный провайдер.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Anthropic SDK — новая dependency | Уже в optional-dependencies, перемещаем в основные |
| OpenAI-compatible провайдеры могут отличаться в деталях | `OpenAICompatibleProvider` имеет override points для provider-specific логики |
| Fallback может скрыть реальные ошибки | Fallback только для retry-able ошибок (rate_limit, timeout). Остальные — propagate |
| Static models для Ollama могут быть stale | Extension point `ModelDiscovery` для future dynamic refresh |
| ConfigOption с 100+ моделями — UX | Группировка по провайдерам в клиенте, поиск |
| Breaking change в `LLMProvider.initialize()` | Мигрируем все провайдеры одновременно, тесты покрывают |

## Migration Plan

1. **Фаза 1:** Создать `llm/models.py`, `llm/registry.py`, `llm/base.py` (новые интерфейсы)
2. **Фаза 2:** Рефакторинг `OpenAIProvider` → `OpenAICompatibleProvider` + наследники
3. **Фаза 3:** Создать `AnthropicProvider`
4. **Фаза 4:** Обновить `config.py`, `di.py`, `orchestrator.py`
5. **Фаза 5:** Обновить `config.py` handler для генерации configOptions
6. **Фаза 6:** Тесты для всех новых компонентов
7. **Фаза 7:** CLI обновления

**Rollback:** Если проблемы — вернуть старую `LLMConfig` и `LLMProvider_` из git. Новые файлы не влияют на старый код до изменения DI.

## Open Questions

1. **Zen/Go base_url** — нужно уточнить у команды OpenCode точные endpoint URLs
2. **Стоимость моделей** — где хранить pricing data? Хардкод или внешний API?
3. **Ollama default models** — какой список моделей считать "популярным"?
4. **Stream completion** — все провайдеры поддерживают streaming? Anthropic — да, Gemini — ограниченно
