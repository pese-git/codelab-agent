## Design

### Архитектура конфигурации агентов

Система конфигурации состоит из 4 компонентов:

1. **AgentConfigLoader** — загрузка из TOML + Markdown с override логикой
2. **AgentConfigResolver** — разрешение defaults из глобальных настроек
3. **AgentRegistry** — реестр + hot reload + регистрация в EventBus
4. **Pydantic модели** — валидация и сериализация

### Override логика

Загрузка выполняется от низшего приоритета к высшему (4→1), каждый источник перезаписывает предыдущий:

```
4. ~/.codelab/codelab.toml definitions    (низший)
3. ~/.codelab/agents/*.md
2. codelab.toml definitions
1. .codelab/agents/*.md                   (высший)
```

### Hot reload flow

```
1. Watchdog detect change → .codelab/agents/*.md или codelab.toml
2. AgentRegistry.reload() → AgentConfigLoader.load_all() + resolve
3. Для удалённых агентов: unregister → publish AgentUnregistered
4. Для новых агентов: register → publish AgentRegistered
5. publish AgentListChanged(added, removed)
6. Подписчики (StrategyDispatcher, TUI, Metrics) реагируют автоматически
```

### Интеграция с существующим кодом

- `AppConfig` из `server/config.py` расширяется полем `agents_global: AgentsGlobalConfig`
- TOML загрузчик переиспользует существующую инфраструктуру конфигурации (`tomllib`, merge logic)
- Watchdog для hot reload — новый компонент (watchdog library)
- Pydantic модели используют существующий стиль валидации проекта
- `SessionState` расширяется новыми полями с defaults — совместимо с существующими session файлами

### TokenSlicer конфигурация

Глобальные настройки TokenSlicer хранятся в `AgentsGlobalConfig`:
- `slicer_model` — модель для суммаризации (дешёвая, по умолчанию gpt-4o-mini)
- `max_sliced_tokens` — лимит токенов для summary (по умолчанию 120)
- `slicer_skip_threshold` — не сжимать если output < N токенов (по умолчанию 300)

TokenSlicer используется в OrchestratedStrategy и HierarchicalStrategy для суммаризации ответов субагентов перед добавлением в контекст координатора.

### Ключевые решения

| Решение | Обоснование |
|---|---|
| Override (не merge) | Предсказуемость — один источник правды для каждого агента |
| Имя файла = имя агента | Просто, как в OpenCode |
| Числовой priority | Проще сортировка, default 99 |
| model_config(extra="allow") | Vendor-specific параметры без изменения схемы |
| Watchdog на 4 источника | Глобальные + проектные, TOML + Markdown |
| SessionState migration с defaults | Совместимость с существующими session файлами |
