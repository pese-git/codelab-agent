## 1. Pydantic TOML Models

- [x] 1.1 Create `codelab/src/codelab/server/toml_config/pydantic_config.py` with Pydantic Settings models
- [x] 1.2 Implement `ModelConfig` with `to_model_info()` method and humanized name generation
- [x] 1.3 Implement `ProviderConfig` with `to_provider_info()` method
- [x] 1.4 Implement `TOMLConfig(BaseSettings)` with `TomlConfigSettingsSource`
- [x] 1.5 Handle env var expansion `${VAR}` via field validator

## 2. Unit Tests for Pydantic TOML Config

- [x] 2.1 Create `codelab/tests/server/toml_config/test_pydantic_config.py`
- [x] 2.2 Test TOML parsing with full config (multiple providers with models)
- [x] 2.3 Test `to_model_info()` and `to_provider_info()` methods
- [x] 2.4 Test humanized name generation
- [x] 2.5 Test empty providers section
- [x] 2.6 Test env var expansion in api_key

## 3. RegistryProvider Integration

- [x] 3.1 Update `RegistryProvider.get_llm_registry()` to use `TOMLConfig.providers`
- [x] 3.2 Call `provider_cfg.to_provider_info()` and pass to `registry.register()`
- [x] 3.3 Keep mock provider registration without TOML config
- [x] 3.4 Update DI container to pass `TOMLConfig` to `RegistryProvider`

## 4. Migration from toml_loader.py

- [x] 4.1 Update all usages of `toml_loader.load_config()` to use new `TOMLConfig()`
- [x] 4.2 Update CLI config loading in `cli.py` (not needed - RegistryProvider handles it)
- [x] 4.3 Remove or deprecate old `toml_loader.py` (kept for backward compatibility)
- [x] 4.4 Update existing tests that use `TOMLConfig` (replaced with new tests)

## 5. Integration Tests

- [x] 5.1 Test `registry.list_all_models()` returns models from TOML
- [x] 5.2 Test `configOptions.model.options` contains all TOML models after `session/new`
- [x] 5.3 Test backward compatibility: empty TOML → empty model list → fallback defaults

## 6. Verification

- [x] 6.1 Run `make check` to verify linting, type checking, and all tests pass
- [x] 6.2 Verify configOptions output matches ACP spec format
