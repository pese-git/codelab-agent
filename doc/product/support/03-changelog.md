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

### MCP Integration (Stage 8)

Добавлена поддержка Model Context Protocol:
- Модуль интеграции с MCP серверами
- Поддержка параметра `mcpServers` в сессиях
- Transport для запуска MCP серверов через stdio
- Адаптер инструментов MCP для ToolRegistry

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

## Roadmap

### Выполнено

- ✅ **Multi-Provider LLM** — 8+ провайдеров, fallback, model switching, TOML config
- ✅ **Global Policy Management** — глобальные политики разрешений (Stage 5)
- ✅ **MCP Integration** — поддержка Model Context Protocol (Stage 8)
- ✅ **Content Types** — полная интеграция типов контента (Stage 4)
- ✅ **Terminal Output Flow** — корректная работа терминала по ACP spec

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
