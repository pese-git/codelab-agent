# Spec: codelab — Delta для Multi-Provider LLM

## ADDED Requirements

### Requirement: TOML конфигурация
Система ДОЛЖНА поддерживать TOML-файлы как основной формат конфигурации LLM-провайдеров, аналогично формату `opencode.json` в OpenCode.

#### Scenario: Загрузка codelab.toml
- **WHEN** файл `codelab.toml` существует в рабочей директории
- **THEN** конфигурация LLM загружается из этого файла

#### Scenario: Загрузка codelab.local.toml
- **WHEN** файл `codelab.local.toml` существует рядом с `codelab.toml`
- **THEN** его значения переопределяют значения из `codelab.toml`

#### Scenario: Загрузка ~/.codelab/auth.toml
- **WHEN** файл `~/.codelab/auth.toml` существует
- **THEN** API keys и секреты загружаются из этого файла как базовый источник

#### Scenario: Приоритет источников конфигурации
- **WHEN** загружается конфигурация
- **THEN** применяется порядок: CLI args > `.env` > `codelab.local.toml` > `codelab.toml` > `~/.codelab/auth.toml` > defaults

#### Scenario: TOML формат моделей как map
- **WHEN** модели определены в TOML как `[llm.providers.openai.models]`
- **THEN** каждая модель — ключ map с optional inline table для overrides: `gpt-4o = { context_window = 128000 }`

### Requirement: Per-model конфигурация
Система ДОЛЖНА поддерживать конфигурацию на уровне каждой модели, включая контекстные лимиты, стоимость и display name.

#### Scenario: Модель с контекстными лимитами
- **WHEN** модель имеет `context_window = 128000` в конфигурации
- **THEN** этот лимит используется при валидации запросов к модели

#### Scenario: Модель с максимальной длиной output
- **WHEN** модель имеет `max_output_tokens = 4096` в конфигурации
- **THEN** этот лимит передаётся в API-запрос как `max_tokens`

#### Scenario: Модель с кастомным display name
- **WHEN** модель имеет `name = "GPT-4o (custom)"` в конфигурации
- **THEN** это имя используется в configOptions вместо дефолтного

#### Scenario: Модель отключена
- **WHEN** модель имеет `enabled = false` в конфигурации
- **THEN** модель не отображается в configOptions и не доступна для выбора

### Requirement: Глобальный файл аутентификации
Система ДОЛЖНА поддерживать глобальный файл `~/.codelab/auth.toml` для хранения API keys, общих для всех проектов.

#### Scenario: API key из глобального файла
- **WHEN** `codelab.toml` не содержит `api_key` для провайдера
- **THEN** API key загружается из `~/.codelab/auth.toml`

#### Scenario: Project-level override для API key
- **WHEN** `codelab.local.toml` содержит `api_key` для провайдера
- **THEN** project-level key переопределяет глобальный key из `~/.codelab/auth.toml`

#### Scenario: Глобальный файл не существует
- **WHEN** `~/.codelab/auth.toml` не существует
- **THEN** загрузка продолжается без ошибки, API keys ожидаются из других источников

## MODIFIED Requirements

### Requirement: Архитектура LLM провайдеров
Система ДОЛЖНА поддерживать несколько LLM-провайдеров через архитектуру на основе реестра вместо одного захардкоженного провайдера.

**Предыдущее поведение:** Единственный `OpenAIProvider` создавался через if/else в DI-контейнере.
**Новое поведение:** `LLMProviderRegistry` управляет регистрацией провайдеров, `ModelResolver` разрешает ссылки `"provider/model"` в конкретные провайдеры.

#### Scenario: Реестр заменяет DI if/else
- **WHEN** DI-контейнер создаёт LLM-зависимости
- **THEN** он создаёт `LLMProviderRegistry` и регистрирует все сконфигурированные провайдеры вместо использования логики if/else

#### Scenario: AgentOrchestrator использует ModelResolver
- **WHEN** `AgentOrchestrator` necesita вызвать LLM
- **THEN** он использует `ModelResolver` для получения провайдера для текущей модели сессии вместо прямой ссылки на `LLMProvider`

#### Scenario: Модель для конкретной сессии
- **WHEN** сессия имеет `config_values["model"] = "anthropic/claude-sonnet-4"`
- **THEN** запросы для этой сессии используют Anthropic провайдер с моделью `claude-sonnet-4`

### Requirement: Структура конфигурации LLM
Система ДОЛЖНА использовать расширенную `LLMConfig` с конфигурацией для каждого провайдера, per-model настройками и настройками fallback.

**Предыдущее поведение:** Плоская конфигурация с полями `provider`, `model`, `api_key`, `base_url`.
**Новое поведение:** `LLMConfig` имеет `providers: dict[str, ProviderConfig]`, `fallback: FallbackConfig`, плюс legacy `provider`/`model` для обратной совместимости. Каждый провайдер имеет `models: dict[str, ModelConfig]`.

#### Scenario: Конфигурация для каждого провайдера
- **WHEN** получен доступ к `LLMConfig.providers["anthropic"]`
- **THEN** возвращён `ProviderConfig` с `api_key`, `base_url`, `default_model`, `enabled`, `timeout`, `max_retries`, `models`

#### Scenario: Per-model конфигурация
- **WHEN** получен доступ к `LLMConfig.providers["openai"].models["gpt-4o"]`
- **THEN** возвращён `ModelConfig` с `context_window`, `max_output_tokens`, `cost_per_1m_input`, `cost_per_1m_output`, `name`

#### Scenario: Конфигурация fallback
- **WHEN** получен доступ к `LLMConfig.fallback`
- **THEN** возвращён `FallbackConfig` с `enabled`, `strategy`, `order`, `retry_on`

#### Scenario: Обратная совместимость
- **WHEN** конфигурация загружена только с `provider="openai"` и `model="gpt-4o"`
- **THEN** применены значения по умолчанию для полей `providers` и `fallback`

### Requirement: Интерфейс LLM Provider
Система ДОЛЖНА обновить `LLMProvider.initialize()` для приёма `LLMConfig` вместо `dict[str, Any]`.

**Предыдущее поведение:** `initialize(config: dict[str, Any])` с нетипизированной конфигурацией.
**Новое поведение:** `initialize(config: LLMConfig)` с типизированной Pydantic конфигурацией.

#### Scenario: Типизированная инициализация
- **WHEN** вызван `provider.initialize(LLMConfig(api_key="sk-...", model="gpt-4o"))`
- **THEN** провайдер инициализирован с типизированной, валидированной конфигурацией

#### Scenario: Все провайдеры используют новый интерфейс
- **WHEN** любой провайдер (`OpenAIProvider`, `AnthropicProvider`, и т.д.) инициализирован
- **THEN** он получает экземпляр `LLMConfig`, а не dict

### Requirement: Генерация ConfigOptions
Система ДОЛЖНА генерировать `configOptions` для выбора модели из всех зарегистрированных провайдеров.

**Предыдущее поведение:** Статические configOptions с захардкоженным списком моделей.
**Новое поведение:** Динамические configOptions, генерируемые из `LLMProviderRegistry.list_all_models()` с учётом per-model конфигурации.

#### Scenario: Динамический список моделей
- **WHEN** ответ `session/new` включает `configOptions`
- **THEN** configOption `model` содержит все модели от всех зарегистрированных провайдеров в формате `"provider/model"`

#### Scenario: Опция модели включает стоимость и контекст
- **WHEN** опции моделей имеют данные о стоимости и контекстных лимитах
- **THEN** поле `description` включает: `"Fast and capable · 128K context · $2.50/M input · $10.00/M output"`

#### Scenario: Кастомное имя модели
- **WHEN** модель имеет `name = "GPT-4o (custom)"` в конфигурации
- **THEN** в configOptions используется это имя вместо дефолтного

### Requirement: Аргументы CLI
Система ДОЛЖНА поддерживать аргументы CLI для конфигурации fallback и переопределения TOML-конфигурации.

**Предыдущее поведение:** CLI аргументы для `--llm-provider`, `--llm-model`, `--llm-api-key` и т.д.
**Новое поведение:** Дополнительные аргументы для `--fallback-enabled`, `--fallback-strategy`, `--fallback-order`, `--config`.

#### Scenario: CLI аргументы fallback
- **WHEN** сервер запущен с `--fallback-enabled --fallback-strategy sequential --fallback-order openai,openrouter,ollama`
- **THEN** цепочка fallback сконфигурирована соответствующим образом

#### Scenario: Custom путь к конфигу
- **WHEN** сервер запущен с `--config /path/to/custom.toml`
- **THEN** конфигурация загружается из указанного файла вместо `codelab.toml`
