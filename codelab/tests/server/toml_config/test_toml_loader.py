"""Тесты для TOML configuration loader."""

import os
from pathlib import Path
from unittest.mock import patch

from codelab.server.toml_config.toml_loader import (
    FallbackConfig,
    ModelConfig,
    ProviderConfig,
    _deep_merge,
    _flatten_dotted_keys,
    _parse_fallback_config,
    _parse_model_config,
    _parse_provider_config,
    _parse_toml_config,
    expand_env_vars,
    load_config,
    load_toml_file,
)


class TestExpandEnvVars:
    """Тесты для expand_env_vars."""

    def test_no_env_vars_unchanged(self) -> None:
        """Строка без переменных окружения не меняется."""
        assert expand_env_vars("hello world") == "hello world"

    def test_empty_string_unchanged(self) -> None:
        """Пустая строка не меняется."""
        assert expand_env_vars("") == ""

    def test_dollar_brace_format(self) -> None:
        """Формат ${VAR_NAME} раскрывается."""
        with patch.dict(os.environ, {"MY_KEY": "secret123"}):
            result = expand_env_vars("${MY_KEY}")
            assert result == "secret123"

    def test_dollar_format(self) -> None:
        """Формат $VAR_NAME раскрывается."""
        with patch.dict(os.environ, {"MY_KEY": "secret123"}):
            result = expand_env_vars("$MY_KEY")
            assert result == "secret123"

    def test_missing_var_replaced_with_empty(self) -> None:
        """Отсутствующая переменная заменяется пустой строкой."""
        with patch.dict(os.environ, {}, clear=True):
            result = expand_env_vars("${NONEXISTENT_VAR}")
            assert result == ""

    def test_multiple_vars_in_string(self) -> None:
        """Несколько переменных в строке раскрываются."""
        with patch.dict(os.environ, {"USER": "alice", "HOST": "localhost"}):
            result = expand_env_vars("https://${USER}@${HOST}/api")
            assert result == "https://alice@localhost/api"

    def test_prefix_suffix_preserved(self) -> None:
        """Префикс и суффикс сохраняются."""
        with patch.dict(os.environ, {"KEY": "abc123"}):
            result = expand_env_vars("Bearer $KEY token")
            assert result == "Bearer abc123 token"

    def test_mixed_format(self) -> None:
        """Смешанные форматы ${VAR} и $VAR."""
        with patch.dict(os.environ, {"A": "1", "B": "2"}):
            result = expand_env_vars("${A}-$B")
            assert result == "1-2"


class TestModelConfig:
    """Тесты для ModelConfig."""

    def test_defaults(self) -> None:
        """Значения по умолчанию None."""
        config = ModelConfig()
        assert config.context_window is None
        assert config.max_output_tokens is None
        assert config.cost_per_input_token is None
        assert config.cost_per_output_token is None

    def test_from_dict(self) -> None:
        """Создание из dict."""
        config = ModelConfig(
            context_window=128000,
            max_output_tokens=16384,
            cost_per_input_token=0.00001,
            cost_per_output_token=0.00003,
        )
        assert config.context_window == 128000
        assert config.max_output_tokens == 16384


class TestProviderConfig:
    """Тесты для ProviderConfig."""

    def test_defaults(self) -> None:
        """Значения по умолчанию."""
        config = ProviderConfig()
        assert config.api_key is None
        assert config.base_url is None
        assert config.default_model is None
        assert config.models == {}


class TestFallbackConfig:
    """Тесты для FallbackConfig."""

    def test_defaults(self) -> None:
        """Значения по умолчанию."""
        config = FallbackConfig()
        assert config.enabled is False
        assert config.strategy == "sequential"
        assert config.order == []
        assert config.max_attempts == 3
        assert config.retry_on == ["rate_limit", "timeout"]


class TestParseModelConfig:
    """Тесты для _parse_model_config."""

    def test_parse_full_config(self) -> None:
        """Парсинг полной конфигурации модели."""
        data = {
            "context_window": 128000,
            "max_output_tokens": 16384,
            "cost_per_input_token": 0.00001,
            "cost_per_output_token": 0.00003,
        }
        config = _parse_model_config(data)
        assert config.context_window == 128000
        assert config.max_output_tokens == 16384

    def test_parse_partial_config(self) -> None:
        """Парсинг частичной конфигурации."""
        data = {"context_window": 128000}
        config = _parse_model_config(data)
        assert config.context_window == 128000
        assert config.max_output_tokens is None

    def test_parse_empty_config(self) -> None:
        """Парсинг пустой конфигурации."""
        config = _parse_model_config({})
        assert config.context_window is None


class TestFlattenDottedKeys:
    """Тесты для _flatten_dotted_keys."""

    def test_flat_dict_unchanged(self) -> None:
        """Плоский dict не меняется."""
        data = {"a": 1, "b": 2}
        result = _flatten_dotted_keys(data)
        assert result == {"a": 1, "b": 2}

    def test_nested_from_dotted_keys(self) -> None:
        """Вложенность от точек распутывается.

        TOML: [models.qwen3.6-plus] → {"qwen3": {"6-plus": {...}}}
        """
        data = {
            "qwen3": {
                "6-plus": {
                    "context_window": 128000,
                    "max_output_tokens": 16384,
                }
            }
        }
        result = _flatten_dotted_keys(data)
        assert "qwen3.6-plus" in result
        assert result["qwen3.6-plus"]["context_window"] == 128000

    def test_real_nested_structure_preserved(self) -> None:
        """Реальная вложенная структура сохраняется."""
        data = {
            "gpt-4o": {
                "context_window": 128000,
                "max_output_tokens": 16384,
            }
        }
        result = _flatten_dotted_keys(data)
        assert "gpt-4o" in result
        assert result["gpt-4o"]["context_window"] == 128000

    def test_non_dict_unchanged(self) -> None:
        """Не-dict значение возвращается как есть."""
        assert _flatten_dotted_keys("hello") == "hello"
        assert _flatten_dotted_keys([1, 2, 3]) == [1, 2, 3]

    def test_multiple_dotted_keys(self) -> None:
        """Несколько dotted keys распутываются."""
        data = {
            "qwen3": {
                "6-plus": {"context_window": 128000},
            },
            "openai": {
                "gpt-4o": {"context_window": 128000},
            },
        }
        result = _flatten_dotted_keys(data)
        assert "qwen3.6-plus" in result
        assert "openai.gpt-4o" in result


class TestParseProviderConfig:
    """Тесты для _parse_provider_config."""

    def test_basic_provider(self) -> None:
        """Базовый провайдер без моделей."""
        data = {
            "api_key": "sk-test",
            "base_url": "https://api.openai.com",
            "default_model": "gpt-4o",
        }
        config = _parse_provider_config(data)
        assert config.api_key == "sk-test"
        assert config.base_url == "https://api.openai.com"
        assert config.default_model == "gpt-4o"
        assert config.models == {}

    def test_env_var_expansion_in_api_key(self) -> None:
        """API key с env var раскрывается."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "real-key-123"}):
            data = {"api_key": "${OPENAI_API_KEY}"}
            config = _parse_provider_config(data)
            assert config.api_key == "real-key-123"

    def test_provider_with_models(self) -> None:
        """Провайдер с моделями."""
        data = {
            "api_key": "sk-test",
            "models": {
                "gpt-4o": {
                    "context_window": 128000,
                    "max_output_tokens": 16384,
                }
            },
        }
        config = _parse_provider_config(data)
        assert "gpt-4o" in config.models
        assert config.models["gpt-4o"].context_window == 128000

    def test_provider_with_dotted_model_names(self) -> None:
        """Провайдер с dotted model names (qwen3.6-plus)."""
        data = {
            "api_key": "sk-test",
            "models": {
                "qwen3": {
                    "6-plus": {
                        "context_window": 128000,
                    }
                }
            },
        }
        config = _parse_provider_config(data)
        assert "qwen3.6-plus" in config.models
        assert config.models["qwen3.6-plus"].context_window == 128000


class TestParseFallbackConfig:
    """Тесты для _parse_fallback_config."""

    def test_defaults(self) -> None:
        """Значения по умолчанию."""
        config = _parse_fallback_config({})
        assert config.enabled is False
        assert config.strategy == "sequential"
        assert config.max_attempts == 3

    def test_full_config(self) -> None:
        """Полная конфигурация."""
        data = {
            "enabled": True,
            "strategy": "sequential",
            "order": ["openai", "openrouter", "ollama"],
            "max_attempts": 5,
            "retry_on": ["rate_limit", "timeout", "connection_error"],
        }
        config = _parse_fallback_config(data)
        assert config.enabled is True
        assert config.order == ["openai", "openrouter", "ollama"]
        assert config.max_attempts == 5

    def test_string_order_comma_separated(self) -> None:
        """String order преобразуется в list."""
        data = {"order": "openai, openrouter, ollama"}
        config = _parse_fallback_config(data)
        assert config.order == ["openai", "openrouter", "ollama"]

    def test_string_retry_on_comma_separated(self) -> None:
        """String retry_on преобразуется в list."""
        data = {"retry_on": "rate_limit, timeout"}
        config = _parse_fallback_config(data)
        assert config.retry_on == ["rate_limit", "timeout"]


class TestDeepMerge:
    """Тесты для _deep_merge."""

    def test_simple_merge(self) -> None:
        """Простой merge двух dict."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self) -> None:
        """Вложенный merge."""
        base = {"llm": {"provider": "mock", "model": "gpt-4o"}}
        override = {"llm": {"model": "gpt-4-turbo"}}
        result = _deep_merge(base, override)
        assert result["llm"]["provider"] == "mock"
        assert result["llm"]["model"] == "gpt-4-turbo"

    def test_override_non_dict_with_dict(self) -> None:
        """Override non-dict значения dict."""
        base = {"llm": "mock"}
        override = {"llm": {"provider": "openai"}}
        result = _deep_merge(base, override)
        assert result["llm"] == {"provider": "openai"}

    def test_empty_override(self) -> None:
        """Empty override возвращает копию base."""
        base = {"a": 1}
        result = _deep_merge(base, {})
        assert result == {"a": 1}
        assert result is not base


class TestLoadTomlFile:
    """Тесты для load_toml_file."""

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        """Несуществующий файл возвращает пустой dict."""
        result = load_toml_file(tmp_path / "nonexistent.toml")
        assert result == {}

    def test_valid_toml_file(self, tmp_path: Path) -> None:
        """Валидный TOML файл загружается."""
        toml_file = tmp_path / "test.toml"
        toml_file.write_text("""
[llm]
provider = "openai"
model = "gpt-4o"
temperature = 0.7
""")
        result = load_toml_file(toml_file)
        assert result["llm"]["provider"] == "openai"
        assert result["llm"]["model"] == "gpt-4o"

    def test_empty_toml_file(self, tmp_path: Path) -> None:
        """Пустой TOML файл загружается как пустой dict."""
        toml_file = tmp_path / "empty.toml"
        toml_file.write_text("")
        result = load_toml_file(toml_file)
        assert result == {}


class TestParseTOMLConfig:
    """Тесты для _parse_toml_config."""

    def test_empty_data_returns_defaults(self) -> None:
        """Пустые данные возвращают defaults."""
        config = _parse_toml_config({})
        assert config.llm_provider == "mock"
        assert config.llm_model == "mock-model"
        assert config.temperature == 0.7
        assert config.max_tokens == 8192
        assert config.providers == {}
        assert isinstance(config.fallback, FallbackConfig)

    def test_full_toml_data(self) -> None:
        """Полные TOML данные парсятся корректно."""
        data = {
            "llm": {
                "provider": "openai",
                "model": "gpt-4o",
                "temperature": 0.9,
                "max_tokens": 4096,
                "providers": {
                    "openai": {
                        "api_key": "sk-test",
                        "base_url": "https://api.openai.com",
                        "default_model": "gpt-4o",
                    }
                },
                "fallback": {
                    "enabled": True,
                    "strategy": "sequential",
                    "order": ["openai", "ollama"],
                },
            }
        }
        config = _parse_toml_config(data)
        assert config.llm_provider == "openai"
        assert config.llm_model == "gpt-4o"
        assert config.temperature == 0.9
        assert config.max_tokens == 4096
        assert "openai" in config.providers
        assert config.providers["openai"].api_key == "sk-test"
        assert config.fallback.enabled is True
        assert config.fallback.order == ["openai", "ollama"]


class TestLoadConfig:
    """Тесты для load_config."""

    def test_no_toml_files_returns_defaults(self, tmp_path: Path) -> None:
        """Нет TOML файлов — возвращает defaults."""
        config = load_config(project_root=tmp_path)
        assert config.llm_provider == "mock"
        assert config.llm_model == "mock-model"

    def test_single_project_toml(self, tmp_path: Path) -> None:
        """Один project TOML загружается."""
        toml = tmp_path / "codelab.toml"
        toml.write_text("""
[llm]
provider = "openai"
model = "gpt-4o"
temperature = 0.9
""")
        config = load_config(project_root=tmp_path)
        assert config.llm_provider == "openai"
        assert config.llm_model == "gpt-4o"
        assert config.temperature == 0.9

    def test_local_override_project_toml(self, tmp_path: Path) -> None:
        """Local TOML override project TOML."""
        project_toml = tmp_path / "codelab.toml"
        project_toml.write_text("""
[llm]
provider = "openai"
model = "gpt-4o"
temperature = 0.7
""")
        local_toml = tmp_path / "codelab.local.toml"
        local_toml.write_text("""
[llm]
temperature = 0.9
""")
        config = load_config(project_root=tmp_path)
        assert config.llm_provider == "openai"
        assert config.temperature == 0.9

    def test_custom_config_highest_priority(self, tmp_path: Path) -> None:
        """Custom config имеет высший приоритет."""
        project_toml = tmp_path / "codelab.toml"
        project_toml.write_text("""
[llm]
provider = "openai"
model = "gpt-4o"
""")
        custom_toml = tmp_path / "custom.toml"
        custom_toml.write_text("""
[llm]
provider = "mock"
""")
        config = load_config(project_root=tmp_path, custom_config_path=custom_toml)
        assert config.llm_provider == "mock"

    def test_custom_config_nonexistent_ignored(self, tmp_path: Path) -> None:
        """Несуществующий custom config игнорируется."""
        config = load_config(
            project_root=tmp_path,
            custom_config_path=tmp_path / "nonexistent.toml",
        )
        assert config.llm_provider == "mock"

    def test_with_providers_and_models(self, tmp_path: Path) -> None:
        """TOML с провайдерами и моделями."""
        toml = tmp_path / "codelab.toml"
        toml.write_text("""
[llm]
provider = "openai"
model = "gpt-4o"

[llm.providers.openai]
api_key = "sk-test"
base_url = "https://api.openai.com"
default_model = "gpt-4o"

[llm.providers.openai.models.gpt-4o]
context_window = 128000
max_output_tokens = 16384
""")
        config = load_config(project_root=tmp_path)
        assert "openai" in config.providers
        assert config.providers["openai"].api_key == "sk-test"
        assert "gpt-4o" in config.providers["openai"].models
        assert config.providers["openai"].models["gpt-4o"].context_window == 128000

    def test_with_fallback_config(self, tmp_path: Path) -> None:
        """TOML с fallback конфигурацией."""
        toml = tmp_path / "codelab.toml"
        toml.write_text("""
[llm]
provider = "openai"

[llm.fallback]
enabled = true
strategy = "sequential"
order = ["openai", "openrouter", "ollama"]
max_attempts = 5
""")
        config = load_config(project_root=tmp_path)
        assert config.fallback.enabled is True
        assert config.fallback.strategy == "sequential"
        assert config.fallback.order == ["openai", "openrouter", "ollama"]
        assert config.fallback.max_attempts == 5
