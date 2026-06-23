## MODIFIED Requirements

### Requirement: Базовый класс OpenAI-Compatible Provider
Система SHALL предоставлять базовый класс `OpenAICompatibleProvider`, от которого наследуются все OpenAI-совместимые провайдеры. Провайдер SHALL нормализовать ключи usage в формате, совместимом с LLMAdapter.

#### Scenario: OpenAI провайдер наследует базовый класс
- **WHEN** создан экземпляр `OpenAIProvider`
- **THEN** он использует `OpenAICompatibleProvider` с `base_url=None` и `default_model="gpt-4o"`

#### Scenario: OpenRouter провайдер использует custom base_url
- **WHEN** создан экземпляр `OpenRouterProvider`
- **THEN** он использует `base_url="https://openrouter.ai/api/v1"`

#### Scenario: Переопределение для конкретного провайдера
- **WHEN** подкласс переопределяет `_prepare_request_params()` в `OpenAICompatibleProvider`
- **THEN** переопределённые параметры используются в API-запросе

#### Scenario: Нормализация usage ключей
- **WHEN** OpenAI provider получает response с `usage.prompt_tokens` и `usage.completion_tokens`
- **THEN** provider ДОЛЖЕН нормализовать ключи в `CompletionResponse.usage`:
  - `prompt_tokens` → `input_tokens`
  - `completion_tokens` → `output_tokens`
  - `total_tokens` остаётся без изменений
- **THEN** `CompletionResponse.usage` ДОЛЖЕН содержать `{"input_tokens": X, "output_tokens": Y, "total_tokens": Z}`

#### Scenario: Usage normalization consistency
- **WHEN** OpenAI provider возвращает CompletionResponse
- **THEN** формат usage ДОЛЖЕН быть идентичен формату Anthropic provider
- **THEN** LLMAdapter._extract_usage() ДОЛЖЕН корректно извлекать токены без provider-specific логики
