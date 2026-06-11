# Spec: Multi-Provider LLM

## ADDED Requirements

### Requirement: Реестр провайдеров
Система ДОЛЖНА предоставлять `LLMProviderRegistry` для управления регистрацией, созданием экземпляров и листингом моделей LLM-провайдеров.

#### Scenario: Регистрация провайдера
- **WHEN** провайдер зарегистрирован через `LLMProviderRegistry.register(provider_id, info, factory)`
- **THEN** информация о провайдере и factory сохранены в реестре

#### Scenario: Получение экземпляра провайдера
- **WHEN** вызван `LLMProviderRegistry.create_provider(provider_id, config)` для зарегистрированного провайдера
- **THEN** создан новый экземпляр провайдера через factory и инициализирован с конфигурацией

#### Scenario: Листинг всех моделей всех провайдеров
- **WHEN** вызван `LLMProviderRegistry.list_all_models()`
- **THEN** возвращён список кортежей `(provider_id, model_id, ModelInfo)` для всех зарегистрированных провайдеров

#### Scenario: Получение информации о провайдере
- **WHEN** вызван `LLMProviderRegistry.get_provider_info(provider_id)` для зарегистрированного провайдера
- **THEN** возвращён объект `ProviderInfo`

#### Scenario: Получение информации о модели
- **WHEN** вызван `LLMProviderRegistry.get_model_info(provider_id, model_id)` для зарегистрированного провайдера и модели
- **THEN** возвращён объект `ModelInfo`

#### Scenario: Неизвестный провайдер
- **WHEN** вызван `get_provider_info()` с незарегистрированным provider_id
- **THEN** возбуждено исключение `ProviderNotFoundError`

### Requirement: Формат ссылки на модель
Система ДОЛЖНА использовать формат `"provider/model"` для идентификации модели в configOptions и конфигурации сессии.

#### Scenario: Парсинг валидной ссылки на модель
- **WHEN** вызван `ModelRef.parse("openai/gpt-4o")`
- **THEN** возвращён `ModelRef(provider_id="openai", model_id="gpt-4o")`

#### Scenario: Парсинг ссылки без провайдера
- **WHEN** вызван `ModelRef.parse("gpt-4o")` (без разделителя "/")
- **THEN** возвращён `ModelRef(provider_id=default_provider, model_id="gpt-4o")`

#### Scenario: Конвертация ссылки на модель в строку
- **WHEN** вызван `str(ModelRef(provider_id="anthropic", model_id="claude-sonnet-4"))`
- **THEN** возвращена строка `"anthropic/claude-sonnet-4"`

### Requirement: Резолвер моделей
Система ДОЛЖНА предоставлять `ModelResolver` для разрешения ссылки на модель в конкретный экземпляр провайдера и имя модели.

#### Scenario: Разрешение ссылки на модель
- **WHEN** вызван `ModelResolver.resolve(ModelRef("openai", "gpt-4o"))`
- **THEN** возвращён кортеж `(LLMProvider_instance, "gpt-4o")`

#### Scenario: Разрешение с конфигурацией провайдера
- **WHEN** разрешается ссылка на модель для провайдера с custom `base_url` и `api_key`
- **THEN** провайдер инициализирован с этими значениями конфигурации

#### Scenario: Разрешение неизвестной модели
- **WHEN** разрешается ссылка на модель, не зарегистрированную в провайдере
- **THEN** возбуждено исключение `ModelNotFoundError`

### Requirement: ConfigOption для выбора модели
Система ДОЛЖНА предоставлять entry в `configOptions` с `category: "model"`, содержащий все доступные модели от всех зарегистрированных провайдеров.

#### Scenario: Построение model configOption
- **WHEN** вызван `ConfigOptionBuilder.build_model_config_option()`
- **THEN** возвращён `ConfigOption` с `id="model"`, `category="model"`, `type="select"`

#### Scenario: Формат значения опции модели
- **WHEN** генерируются опции моделей
- **THEN** `value` каждой опции в формате `"provider_id/model_id"` (например, `"openai/gpt-4o"`)

#### Scenario: Описание модели включает стоимость
- **WHEN** генерируются опции моделей с данными о стоимости
- **THEN** `description` каждой опции включает информацию о стоимости: `"Description · $X.XX/M input · $Y.YY/M output"`

#### Scenario: Текущее значение отражает активную модель
- **WHEN** строится model configOption для сессии с активной моделью `"anthropic/claude-sonnet-4"`
- **THEN** `currentValue` установлен в `"anthropic/claude-sonnet-4"`

### Requirement: Переключение модели через Config Option
Система ДОЛЖНА позволять переключать активную модель во время сессии через `session/set_config_option` с `configId="model"`.

#### Scenario: Переключение модели внутри одного провайдера
- **WHEN** клиент вызывает `session/set_config_option` с `configId="model"`, `value="openai/gpt-4o-mini"`
- **THEN** конфигурация сессии обновлена: `llm_provider="openai"`, `llm_model="gpt-4o-mini"`, `model="openai/gpt-4o-mini"`

#### Scenario: Переключение на другой провайдер
- **WHEN** клиент вызывает `session/set_config_option` с `configId="model"`, `value="anthropic/claude-sonnet-4"`
- **THEN** конфигурация сессии обновлена: `llm_provider="anthropic"`, `llm_model="claude-sonnet-4"`, `model="anthropic/claude-sonnet-4"`

#### Scenario: Уведомление после переключения модели
- **WHEN** модель изменена через `set_config_option`
- **THEN** отправлено уведомление `config_option_update` клиенту с полным обновлённым списком configOptions

#### Scenario: Невалидное значение модели
- **WHEN** клиент вызывает `set_config_option` с `configId="model"` и незарегистрированным значением
- **THEN** возвращён ответ с ошибкой с кодом `-32602` (Invalid params)

### Requirement: Конфигурация провайдеров
Система ДОЛЖНА поддерживать конфигурацию для каждого провайдера, включая `api_key`, `base_url`, `default_model`, `enabled`, `timeout` и `max_retries`.

#### Scenario: Провайдер с custom base_url
- **WHEN** провайдер сконфигурирован с `base_url="https://custom.api.example.com/v1"`
- **THEN** провайдер использует этот base_url для всех API-запросов

#### Scenario: Отключённый провайдер
- **WHEN** провайдер имеет `enabled=false` в конфигурации
- **THEN** провайдер не зарегистрирован в реестре и не доступен в configOptions

#### Scenario: Провайдер с whitelist моделей
- **WHEN** провайдер имеет `models=["gpt-4o", "gpt-4o-mini"]` в конфигурации
- **THEN** только эти модели отображаются в configOptions для данного провайдера

### Requirement: Per-model конфигурация
Система ДОЛЖНА поддерживать конфигурацию на уровне каждой модели, включая `context_window`, `max_output_tokens`, `cost_per_1m_input`, `cost_per_1m_output`, `name` и `enabled`.

#### Scenario: Модель с контекстными лимитами
- **WHEN** модель имеет `context_window = 128000` в конфигурации
- **THEN** этот лимит используется при валидации запросов к модели

#### Scenario: Модель с максимальной длиной output
- **WHEN** модель имеет `max_output_tokens = 4096` в конфигурации
- **THEN** этот лимит передаётся в API-запрос как `max_tokens`

#### Scenario: Модель с кастомным display name
- **WHEN** модель имеет `name = "GPT-4o (custom)"` в конфигурации
- **THEN** в configOptions используется это имя вместо дефолтного

#### Scenario: Отключённая модель
- **WHEN** модель имеет `enabled = false` в конфигурации
- **THEN** модель не отображается в configOptions и не доступна для выбора

### Requirement: Базовый класс OpenAI-Compatible Provider
Система ДОЛЖНА предоставлять базовый класс `OpenAICompatibleProvider`, от которого наследуются все OpenAI-совместимые провайдеры.

#### Scenario: OpenAI провайдер наследует базовый класс
- **WHEN** создан экземпляр `OpenAIProvider`
- **THEN** он использует `OpenAICompatibleProvider` с `base_url=None` и `default_model="gpt-4o"`

#### Scenario: OpenRouter провайдер использует custom base_url
- **WHEN** создан экземпляр `OpenRouterProvider`
- **THEN** он использует `base_url="https://openrouter.ai/api/v1"`

#### Scenario: Переопределение для конкретного провайдера
- **WHEN** подкласс переопределяет `_prepare_request_params()` в `OpenAICompatibleProvider`
- **THEN** переопределённые параметры используются в API-запросе

### Requirement: Anthropic Provider
Система ДОЛЖНА предоставлять `AnthropicProvider`, использующий Anthropic Messages API.

#### Scenario: Запрос completion через Anthropic
- **WHEN** вызван `AnthropicProvider.create_completion()`
- **THEN** используется `anthropic` SDK Messages API с установленным `max_tokens`

#### Scenario: Формат инструментов Anthropic
- **WHEN** инструменты переданы в `AnthropicProvider.create_completion()`
- **THEN** инструменты конвертированы в формат Anthropic с `input_schema` вместо `parameters`

#### Scenario: Stop reasons Anthropic
- **WHEN** ответ Anthropic имеет `stop_reason="tool_use"`
- **THEN** он маппится на `LLMResponse.stop_reason="tool_use"`

### Requirement: Шина событий провайдеров
Система ДОЛЖНА предоставлять `ProviderEventBus` для отправки событий жизненного цикла провайдеров.

#### Scenario: Событие инициализации провайдера
- **WHEN** провайдер успешно инициализирован
- **THEN** отправлено событие `ProviderInitialized` через шину событий

#### Scenario: Событие ошибки провайдера
- **WHEN** провайдер не смог инициализироваться или обработать запрос
- **THEN** отправлено событие `ProviderFailed` с деталями ошибки

#### Scenario: Событие обновления моделей
- **WHEN** доступные модели провайдера обновлены (например, dynamic discovery)
- **THEN** отправлено событие `ModelsUpdated` с новым списком моделей

### Requirement: Обновление интерфейса LLM Provider
Система ДОЛЖНА обновить `LLMProvider.initialize()` для приёма `LLMConfig` вместо `dict[str, Any]`.

#### Scenario: Инициализация с типизированной конфигурацией
- **WHEN** вызван `provider.initialize(LLMConfig(api_key="...", model="gpt-4o"))`
- **THEN** провайдер инициализирован с типизированной конфигурацией

#### Scenario: Обратная совместимость
- **WHEN** существующие провайдеры мигрированы на новый интерфейс
- **THEN** все существующие тесты проходят без изменения логики тестов
