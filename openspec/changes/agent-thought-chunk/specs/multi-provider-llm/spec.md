## MODIFIED Requirements

### Requirement: Базовый класс OpenAI-Compatible Provider
Система SHALL предоставлять базовый класс `OpenAICompatibleProvider`, от которого наследуются все OpenAI-совместимые провайдеры. Класс SHALL поддерживать извлечение reasoning из ответов.

#### Scenario: OpenAI провайдер наследует базовый класс
- **WHEN** создан экземпляр `OpenAIProvider`
- **THEN** он использует `OpenAICompatibleProvider` с `base_url=None` и `default_model="gpt-4o"`

#### Scenario: OpenRouter провайдер использует custom base_url
- **WHEN** создан экземпляр `OpenRouterProvider`
- **THEN** он использует `base_url="https://openrouter.ai/api/v1"`

#### Scenario: Переопределение для конкретного провайдера
- **WHEN** подкласс переопределяет `_prepare_request_params()` в `OpenAICompatibleProvider`
- **THEN** переопределённые параметры используются в API-запросе

#### Scenario: Извлечение reasoning из ответа
- **WHEN** провайдер получает ответ от API
- **WHEN** ответ содержит reasoning/reasoning_content
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН содержать извлечённый текст

### Requirement: Anthropic Provider
Система SHALL предоставлять `AnthropicProvider`, использующий Anthropic Messages API. Провайдер SHALL поддерживать извлечение thinking content blocks.

#### Scenario: Запрос completion через Anthropic
- **WHEN** вызван `AnthropicProvider.create_completion()`
- **THEN** используется `anthropic` SDK Messages API с установленным `max_tokens`

#### Scenario: Формат инструментов Anthropic
- **WHEN** инструменты переданы в `AnthropicProvider.create_completion()`
- **THEN** инструменты конвертированы в формат Anthropic с `input_schema` вместо `parameters`

#### Scenario: Stop reasons Anthropic
- **WHEN** ответ Anthropic имеет `stop_reason="tool_use"`
- **THEN** он маппится на `LLMResponse.stop_reason="tool_use"`

#### Scenario: Извлечение thinking blocks
- **WHEN** ответ Anthropic содержит content blocks с `type="thinking"`
- **THEN** `AnthropicProvider` ДОЛЖЕН извлечь текст из thinking blocks
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН содержать агрегированный thinking текст

#### Scenario: Streaming с thinking
- **WHEN** streaming ответ Anthropic содержит thinking content blocks
- **THEN** `AnthropicProvider` ДОЛЖЕН агрегировать thinking chunks
- **THEN** `CompletionResponse.reasoning` ДОЛЖЕН содержать полный текст
