## 1. Pydantic TOML Models

- [ ] 1.1 Create `codelab/src/codelab/server/toml_config/pydantic_config.py` with Pydantic Settings models
- [ ] 1.2 Implement `ModelConfig` with `to_model_info()` method and humanized name generation
- [ ] 1.3 Implement `ProviderConfig` with `to_provider_info()` method
- [ ] 1.4 Implement `TOMLConfig(BaseSettings)` with `TomlConfigSettingsSource`
- [ ] 1.5 Handle env var expansion `${VAR}` via field validator

## 2. Unit Tests for Pydantic TOML Config

- [ ] 2.1 Create `codelab/tests/server/toml_config/test_pydantic_config.py`
- [ ] 2.2 Test TOML parsing with full config (multiple providers with models)
- [ ] 2.3 Test `to_model_info()` and `to_provider_info()` methods
- [ ] 2.4 Test humanized name generation
- [ ] 2.5 Test empty providers section
- [ ] 2.6 Test env var expansion in api_key

## 3. RegistryProvider Integration

- [ ] 3.1 Update `RegistryProvider.get_llm_registry()` to use `TOMLConfig.providers`
- [ ] 3.2 Call `provider_cfg.to_provider_info()` and pass to `registry.register()`
- [ ] 3.3 Keep mock provider registration without TOML config
- [ ] 3.4 Update DI container to pass `TOMLConfig` to `RegistryProvider`

## 4. Migration from toml_loader.py

- [ ] 4.1 Update all usages of `toml_loader.load_config()` to use new `TOMLConfig()`
- [ ] 4.2 Update CLI config loading in `cli.py`
- [ ] 4.3 Remove or deprecate old `toml_loader.py`
- [ ] 4.4 Update existing tests that use `TOMLConfig`

## 5. Integration Tests

- [ ] 5.1 Test `registry.list_all_models()` returns models from TOML
- [ ] 5.2 Test `configOptions.model.options` contains all TOML models after `session/new`
- [ ] 5.3 Test backward compatibility: empty TOML → empty model list → fallback defaults

## 6. Verification

- [ ] 6.1 Run `make check` to verify linting, type checking, and all tests pass
- [ ] 6.2 Verify configOptions output matches ACP spec format
