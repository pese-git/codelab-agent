## Context

Текущая архитектура имеет разрыв между TOML-конфигурацией и LLM Registry:

1. **TOML-конфиг** (`codelab.toml.example`) содержит полное описание провайдеров и моделей
2. **toml_loader.py** — кастомный парсер на `dataclass` + `tomllib`, вручную парсит TOML
3. **LLMProviderRegistry** хранит `_provider_info`, но при регистрации `info=None`
4. **ConfigOptionBuilder** вызывает `list_all_models()` → пустой список

Проект уже использует `pydantic-settings` (v2.14.0), который поддерживает TOML через `TomlConfigSettingsSource`.

## Goals / Non-Goals

**Goals:**
- Использовать Pydantic Settings для парсинга TOML вместо кастомного `toml_loader.py`
- Встроить метод `to_provider_info()` прямо в Pydantic-модели
- Заполнить Registry при старте через `RegistryProvider`
- `configOptions.model.options` содержит все модели из TOML-конфига

**Non-Goals:**
- Dynamic discovery через API провайдеров
- Изменение формата TOML-конфига
- Изменение wire-формата ACP протокола

## Decisions

### 1. Pydantic Settings вместо ConfigMapper

**Решение:** Переписать TOML-модели на Pydantic Settings с `TomlConfigSettingsSource`. Добавить метод `to_provider_info()` как instance method моделей.

**Альтернативы:**
- A) Отдельный `ConfigMapper` — дополнительный слой трансформации, дублирование логики
- B) Расширение существующего `toml_loader.py` — остаётся кастомный парсер без валидации Pydantic

**Рациональ:** Pydantic Settings даёт встроенную валидацию, type checking, env var support, и TOML parsing из коробки. Метод `to_provider_info()` внутри моделей — чистая инкапсуляция.

### 2. Структура Pydantic моделей

```python
class ModelConfig(BaseModel):
    context_window: int | None = None
    max_output_tokens: int | None = None
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None

    def to_model_info(self, model_id: str, provider_id: str) -> ModelInfo:
        return ModelInfo(
            id=model_id,
            provider_id=provider_id,
            name=self._humanize_name(model_id),
            context_window=self.context_window,
            max_output_tokens=self.max_output_tokens,
            cost_per_input_token=self.cost_per_input_token,
            cost_per_output_token=self.cost_per_output_token,
        )

class ProviderConfig(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    models: dict[str, ModelConfig] = {}

    def to_provider_info(self, provider_id: str) -> ProviderInfo:
        models = [
            model_cfg.to_model_info(model_id, provider_id)
            for model_id, model_cfg in self.models.items()
        ]
        return ProviderInfo(
            id=provider_id,
            name=provider_id.title(),
            base_url=self.base_url,
            models=models,
        )

class TOMLConfig(BaseSettings):
    llm_provider: str = "mock"
    llm_model: str = "mock-model"
    temperature: float = 0.7
    max_tokens: int = 8192
    providers: dict[str, ProviderConfig] = {}
    fallback: FallbackConfig = FallbackConfig()

    model_config = SettingsConfigDict(
        env_prefix="CODELAB_",
        toml_file="codelab.toml",
        extra="ignore",
    )
```

### 3. Обновление RegistryProvider

```python
class RegistryProvider(Provider):
    @provide(scope=Scope.APP)
    def get_llm_registry(
        self,
        toml_config: TOMLConfig,
    ) -> LLMProviderRegistry:
        registry = LLMProviderRegistry()

        # Зарегистрировать провайдеры из TOML с ProviderInfo
        for provider_id, provider_cfg in toml_config.providers.items():
            provider_info = provider_cfg.to_provider_info(provider_id)
            factory = self._get_provider_factory(provider_id)
            registry.register(provider_id, factory, info=provider_info)

        # Mock провайдер без TOML config
        if "mock" not in registry.get_registered_providers():
            registry.register("mock", lambda: MockLLMProvider())

        return registry
```

### 4. Humanized name generation

Простая логика: `gpt-4o` → `Gpt 4o`, `claude-sonnet-4` → `Claude Sonnet 4`. Replace `-`/`_` на пробел, title case.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Pydantic Settings может не поддерживать nested `dict[str, ModelConfig]` | Протестировать заранее, fallback на custom parsing если нужно |
| Изменение API TOMLConfig сломает существующий код | Обновить все места использования, тесты поймают |
| Env var expansion `${VAR}` не встроен в Pydantic Settings | Использовать `@field_validator` или custom settings source |

## Migration Plan

1. Создать новые Pydantic модели рядом со старыми `dataclass`
2. Обновить `RegistryProvider` для использования новых моделей
3. Заменить вызовы `toml_loader.load_config()` на `TOMLConfig()`
4. Удалить старый `toml_loader.py`
5. Обновить тесты

Rollback: вернуть `toml_loader.py` и старый `RegistryProvider`.

## Open Questions

- Нужно ли поддерживать env var expansion `${VAR}` в Pydantic Settings? (да, через custom validator)
- Стоит ли объединить `config.py` (`AppConfig`) и новую `TOMLConfig`? (пока нет — разделить ответственность)
