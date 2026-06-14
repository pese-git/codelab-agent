# История изменений

Все значительные изменения в CodeLab документируются в этом разделе.

Полная история изменений доступна в файле [CHANGELOG.md](../../../CHANGELOG.md) в корне репозитория.

## Формат версий

Проект следует [Semantic Versioning](https://semver.org/spec/v2.0.0.html):
- **MAJOR** — несовместимые изменения API
- **MINOR** — новая функциональность с обратной совместимостью
- **PATCH** — исправления ошибок

## Последние изменения

### Multi-Provider LLM Architecture

Полная переработка LLM подсистемы:
- **8+ провайдеров**: OpenAI, Anthropic, OpenRouter, Zen, Go, Ollama, LMStudio, Mock
- **Registry паттерн**: `LLMProviderRegistry` с factory-функциями для ленивой инициализации
- **Model Resolver**: Резолвинг `"provider/model"` в конкретный провайдер
- **Fallback цепочки**: Sequential fallback с Circuit Breaker
- **Model Discovery**: Static discovery с extension point для dynamic
- **Telemetry**: NoOpTelemetry с extension point для Prometheus/Datadog
- **ProviderEventBus**: Шина событий для lifecycle monitoring
- **TOML конфигурация**: `codelab.toml` с multi-level merge
- **Model switching**: Переключение модели mid-session через `session/set_config_option`
- **OpenAICompatibleProvider**: Базовый класс для всех OpenAI-совместимых провайдеров
- **AnthropicProvider**: Отдельная реализация через Messages API

### MCP Integration (Stage 8) — ЗАВЕРШЕНО

Добавлена полная поддержка Model Context Protocol:
- **MCPManager** — управление несколькими MCP-серверами на сессию
- **MCPClient** — клиент с state machine (Created → Connecting → Initializing → Ready)
- **3 транспорта**: StdioTransport, HttpTransport, SseTransport
- **MCPToolAdapter** — адаптация MCP инструментов с kind inference
- **MCPResourceMapper** — MCP resources → ACP ResourceLinkContent
- **MCPPromptMapper** — MCP prompts → slash commands
- **Auto-reconnect** — с exponential backoff (1s → 30s + jitter 10%)
- **Health checks** — проверка состояния MCP-серверов
- **Notifications** — tools/resources/prompts list_changed, progress
- **Roots** — поддержка roots/list и notifications
- **TOML Config** — загрузка MCP-серверов из `codelab.toml` с env variable expansion
- **SessionRuntimeRegistry** — REQUEST-scoped реестр runtime объектов
- **Тесты**: 150+ MCP тестов

### Advanced Permission Management (Stage 5)

Улучшенная система управления разрешениями:
- Автоматическое восстановление политик при загрузке сессии
- Поддержка глобальных политик разрешений
- Интеграционные тесты для persistence

### Content Integration (Stage 4)

Полная поддержка типов контента ACP:
- Text, Diff, Image, Audio content
- Embedded resources и Resource links
- E2E тестирование всех типов контента

### Permission Flow (Stage 3)

Реализована система разрешений:
- Inline widgets для запроса разрешений
- Модальные окна разрешений
- Allow/Reject once и always политики

### Observability Layer

Добавлен observability layer для мониторинга и трассировки:
- **Tracer** — distributed tracing с spans и trace IDs
- **EventTimeline** — хронология событий сессии
- **MetricsTracker** — сбор метрик + auto-log, TelemetrySink
- **FileEventExporter** — экспорт событий в JSON-файл
- **FileMetricsExporter** — экспорт метрик в JSON-файл
- **FileSpanExporter** — экспорт spans в JSON-файл

### Pipeline System (7 стадий)

Замена монолитного PromptOrchestrator на pipeline:
1. ValidationStage → 2. SlashCommandStage → 3. PlanBuildingStage → 4. TurnLifecycleStage(open) → 5. DirectivesStage → 6. LLMLoopStage → 7. TurnLifecycleStage(close)

### AgentLoop + SingleStrategy

Унифицированный цикл LLM tool-calling итераций:
- **AgentLoop** — единый цикл с обработкой tool_calls, permission pause/resume, cancellation
- **SingleStrategy** — единственная реализованная стратегия LLM-вызовов
- **StrategyDispatcher** — диспетчер стратегий с priority chain + fallback
- **StopReason** — ACP-compliant: `end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled`

### Тесты

- **3,302** тестовых метода (+1,502 с момента последней документации)
- **196** тестовых файлов
- Покрытие: unit, integration, E2E (24 теста для 6 content types)

## Roadmap

### Выполнено

- ✅ **Multi-Provider LLM** — 8+ провайдеров, fallback, model switching, TOML config
- ✅ **Global Policy Management** — глобальные политики разрешений (Stage 5)
- ✅ **MCP Integration** — полная поддержка: 3 транспорта, auto-reconnect, roots, resources, prompts, TOML config (Stage 8)
- ✅ **Content Types** — полная интеграция типов контента (Stage 4)
- ✅ **Terminal Output Flow** — корректная работа терминала по ACP spec
- ✅ **Pipeline System** — 7-stage pipeline для обработки промптов
- ✅ **AgentLoop** — унифицированный цикл LLM tool-calling
- ✅ **Observability** — Tracer, Metrics, Timeline, File Exporters
- ✅ **Stdio Transport** — полный паритет с WebSocket (background prompt, deadlock fix)
- ✅ **TOML Configuration** — 4-level hierarchy с env expansion
- ✅ **14 ViewModels** — 9 базовых + 5 selector ViewModels
- ✅ **3,302 теста** — unit, integration, E2E

### Планируется

- **Plugin System** — расширяемая архитектура плагинов
- **Multi-agent** — поддержка нескольких агентов
- **Advanced Plan Management** — улучшенное управление планами

## Обратная совместимость

CodeLab стремится поддерживать обратную совместимость:
- CLI интерфейс стабилен
- Формат сессий версионируется
- Протокол ACP следует официальной спецификации

## Как отслеживать изменения

### GitHub Releases

Следите за [релизами](https://github.com/pese-git/codelab-ai/releases) на GitHub.

### Changelog

Читайте полный [CHANGELOG.md](../../../CHANGELOG.md) для детальной истории изменений.

### Обновление

```bash
cd codelab
git pull origin main
uv sync
```

## См. также

- [CHANGELOG.md](../../../CHANGELOG.md) — полная история изменений
- [Установка](../getting-started/02-installation.md) — руководство по установке
- [Contributing](../developer-guide/06-contributing.md) — как внести вклад
