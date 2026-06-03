## Why

При создании/загрузке сессии ACP протокол возвращает `configOptions` с конфигурацией модели (категория `model`). Однако `ConfigOptionBuilder.build_model_config_option()` вызывает `LLMProviderRegistry.list_all_models()`, который возвращает **пустой список**, потому что провайдеры регистрируются без `ProviderInfo`:

```python
# codelab/src/codelab/server/di.py
registry.register("openai", lambda: OpenAIProvider())  # info=None
registry.register("mock", lambda: MockLLMProvider())   # info=None
```

Метод `list_all_models()` читает модели из `_provider_info`, который остаётся пустым. В результате клиент получает `configOptions` с `model`, содержащим **0 доступных опций** — пользователь не может выбрать модель через UI.

При этом TOML-конфиг (`codelab.toml.example`) уже содержит богатое описание всех моделей (context_window, max_output_tokens, pricing), но эти данные не попадают в Registry.

## What Changes

- Переписать `TOMLConfig` и связанные модели на Pydantic Settings с `TomlConfigSettingsSource`
- Добавить метод `to_provider_info()` в Pydantic-модели для создания `ProviderInfo`/`ModelInfo`
- Обновить `RegistryProvider` для использования нового метода при регистрации провайдеров
- Удалить или упростить кастомный `toml_loader.py` (заменить на Pydantic Settings)
- `configOptions` для `model` будет содержать все модели из TOML-конфига
- Добавить тесты на корректность заполнения config options моделями

## Capabilities

### New Capabilities
- `pydantic-toml-config`: Использование Pydantic Settings с `TomlConfigSettingsSource` для парсинга TOML-конфигурации провайдеров и моделей, включая встроенный метод `to_provider_info()` для создания `ProviderInfo`/`ModelInfo`

### Modified Capabilities
- `session-config-options`: `configOptions` для категории `model` теперь содержит реальный список моделей из конфигурации вместо пустого списка

## Impact

**Affected files:**
- `codelab/src/codelab/server/toml_config/toml_loader.py` → заменить на Pydantic Settings модели
- `codelab/src/codelab/server/di.py` — обновление `RegistryProvider`
- `codelab/src/codelab/server/config.py` — возможно объединение с новой TOML-конфигурацией
- `codelab/tests/server/` — новые тесты Pydantic TOML parsing и config options

**API changes:** None (внутреннее изменение, wire-формат ACP не меняется)

**Dependencies:** `pydantic-settings` уже установлен в проекте (v2.14.0)
