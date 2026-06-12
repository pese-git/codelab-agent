## ADDED Requirements

### Requirement: Pydantic TOML Configuration

> **Архитектурное решение:** Вместо `TomlConfigSettingsSource` из `pydantic-settings`
> используется ручной парсинг через `tomllib` + deep merge нескольких файлов.
> Это необходимо потому что проект использует multi-file merge chain
> (auth.toml → codelab.toml → codelab.local.toml → custom) с deep merge и env var
> expansion, что `TomlConfigSettingsSource` не поддерживает.

Система ДОЛЖНА использовать Pydantic модели для валидации TOML конфигурации,
заменяя кастомные dataclass из `toml_loader.py`.

#### Scenario: TOML file parsing with Pydantic Settings
- **WHEN** `TOMLConfig()` is instantiated with a valid `codelab.toml` file
- **THEN** all providers and models are parsed into Pydantic model instances
- **AND** validation errors are raised for invalid TOML structure
- **AND** environment variables in `api_key` fields are expanded via field validator

#### Scenario: Nested provider and model configuration
- **WHEN** TOML contains `[llm.providers.openai.models.gpt-4o]` section
- **THEN** `TOMLConfig.providers["openai"].models["gpt-4o"]` contains a `ModelConfig` instance
- **AND** `context_window`, `max_output_tokens` values are correctly parsed

#### Scenario: Empty providers section
- **WHEN** TOML has no `[llm.providers]` section
- **THEN** `TOMLConfig.providers` is an empty dict
- **AND** no exception is raised

#### Scenario: Provider without models
- **WHEN** a provider is defined in TOML but has no `models` subsection
- **THEN** `ProviderConfig.models` is an empty dict
- **AND** the provider is still included in `TOMLConfig.providers`

### Requirement: ProviderInfo Generation from Pydantic Models
Each Pydantic configuration model SHALL provide a `to_provider_info()` method that converts the model data into `ProviderInfo` and `ModelInfo` objects for `LLMProviderRegistry` registration.

#### Scenario: ModelConfig.to_model_info() generates ModelInfo
- **WHEN** `ModelConfig.to_model_info(model_id, provider_id)` is called
- **THEN** it returns a `ModelInfo` with correct `id`, `provider_id`, and metadata
- **AND** `ModelInfo.full_id` returns `provider_id/model_id` format
- **AND** `context_window` and `max_output_tokens` are copied from the model config

#### Scenario: ProviderConfig.to_provider_info() generates ProviderInfo
- **WHEN** `ProviderConfig.to_provider_info(provider_id)` is called
- **THEN** it returns a `ProviderInfo` with all models from `self.models`
- **AND** each model's `to_model_info()` is called with correct parameters
- **AND** `ProviderInfo.name` is a humanized version of `provider_id`

#### Scenario: Human-readable model name generation
- **WHEN** `to_model_info()` generates a model name from ID
- **THEN** hyphens and underscores are replaced with spaces
- **AND** title case is applied
- **AND** `gpt-4o` becomes `Gpt 4o`
- **AND** `llama3_1_70b` becomes `Llama3 1 70b`
- **AND** `claude-sonnet-4` becomes `Claude Sonnet 4`

#### Scenario: Environment variable expansion in api_key
- **WHEN** `api_key` contains `${OPENAI_API_KEY}` format
- **THEN** the field validator expands it to the actual environment variable value
- **AND** if the environment variable is not set, the value becomes empty string

### Requirement: DI Integration для регистрации провайдеров

`RegistryProvider` (в DI контейнере) ДОЛЖЕН использовать `config.llm.providers`
и вызывать `to_provider_info()` для каждого провайдера чтобы заполнить
`LLMProviderRegistry` с `ProviderInfo` содержащим модели.

#### Scenario: Registry populated with TOML models
- **WHEN** `RegistryProvider.get_llm_registry()` вызван с конфигурацией содержащей провайдеры
- **THEN** registry `list_all_models()` возвращает все модели из TOML
- **AND** `get_provider_info(provider_id)` возвращает правильный `ProviderInfo` для каждого провайдера

#### Scenario: Mock provider without TOML config
- **WHEN** `mock` provider is not defined in TOML
- **THEN** it is still registered in the registry with `info=None`
- **AND** `list_all_models()` does not include mock models

#### Scenario: Registry backward compatibility
- **WHEN** `TOMLConfig` has no providers section
- **THEN** registry is created with only default providers (mock)
- **AND** `list_all_models()` returns empty list (fallback to default config specs)

### Requirement: Config Options Population
The `configOptions` returned during session setup SHALL include all models from `LLMProviderRegistry` in the `model` config option.

#### Scenario: Session new returns model options
- **WHEN** `session/new` is called and registry contains models from TOML
- **THEN** the response `configOptions` includes a `model` option with all registered models
- **AND** each model option has `value`, `label`, and `description` fields

#### Scenario: Model option format matches ACP spec
- **WHEN** a model option is built for `configOptions`
- **THEN** `value` is the model's `full_id` (e.g., `openai/gpt-4o`)
- **AND** `label` is the model's `name`
- **AND** `description` includes context window if available
