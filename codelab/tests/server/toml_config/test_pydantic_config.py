"""Unit tests for Pydantic TOML configuration models."""

from __future__ import annotations

import os
from unittest.mock import patch

from codelab.server.llm.models import ModelInfo, ProviderInfo
from codelab.server.toml_config.pydantic_config import (
    FallbackConfig,
    ModelConfig,
    ProviderConfig,
    TimeoutConfig,
    _expand_env_vars,
    _humanize_name,
)


class TestHumanizeName:
    """Tests for _humanize_name function."""

    def test_simple_model_name(self) -> None:
        assert _humanize_name("gpt-4o") == "Gpt 4O"

    def test_underscore_separated(self) -> None:
        assert _humanize_name("llama3_1_70b") == "Llama3 1 70B"

    def test_hyphen_separated(self) -> None:
        assert _humanize_name("claude-sonnet-4") == "Claude Sonnet 4"

    def test_mixed_separators(self) -> None:
        assert _humanize_name("my_custom-model") == "My Custom Model"

    def test_no_separators(self) -> None:
        assert _humanize_name("gpt4") == "Gpt4"

    def test_single_word(self) -> None:
        assert _humanize_name("model") == "Model"


class TestExpandEnvVars:
    """Tests for _expand_env_vars function."""

    def test_no_env_vars(self) -> None:
        assert _expand_env_vars("plain-text") == "plain-text"

    def test_dollar_brace_format(self) -> None:
        with patch.dict(os.environ, {"TEST_KEY": "secret123"}):
            assert _expand_env_vars("${TEST_KEY}") == "secret123"

    def test_dollar_format(self) -> None:
        with patch.dict(os.environ, {"TEST_KEY": "secret123"}):
            assert _expand_env_vars("$TEST_KEY") == "secret123"

    def test_missing_env_var(self) -> None:
        assert _expand_env_vars("${MISSING_VAR}") == ""

    def test_mixed_content(self) -> None:
        with patch.dict(os.environ, {"API_KEY": "key123"}):
            result = _expand_env_vars("prefix-${API_KEY}-suffix")
            assert result == "prefix-key123-suffix"

    def test_empty_string(self) -> None:
        assert _expand_env_vars("") == ""

    def test_none_value(self) -> None:
        # None is not a string, so it returns as-is
        assert _expand_env_vars(None) is None  # type: ignore


class TestModelConfig:
    """Tests for ModelConfig model."""

    def test_default_values(self) -> None:
        config = ModelConfig()
        assert config.context_window is None
        assert config.max_output_tokens is None
        assert config.cost_per_input_token is None
        assert config.cost_per_output_token is None

    def test_with_values(self) -> None:
        config = ModelConfig(
            context_window=128000,
            max_output_tokens=16384,
            cost_per_input_token=0.0000025,
            cost_per_output_token=0.00001,
        )
        assert config.context_window == 128000
        assert config.max_output_tokens == 16384

    def test_to_model_info(self) -> None:
        config = ModelConfig(context_window=128000, max_output_tokens=16384)
        info = config.to_model_info("gpt-4o", "openai")

        assert isinstance(info, ModelInfo)
        assert info.id == "gpt-4o"
        assert info.provider_id == "openai"
        assert info.name == "Gpt 4O"
        assert info.context_window == 128000
        assert info.max_output_tokens == 16384
        assert info.full_id == "openai/gpt-4o"


class TestProviderConfig:
    """Tests for ProviderConfig model."""

    def test_default_values(self) -> None:
        config = ProviderConfig()
        assert config.api_key is None
        assert config.base_url is None
        assert config.default_model is None
        assert config.models == {}

    def test_env_var_expansion_in_api_key(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-123"}):
            config = ProviderConfig(api_key="${OPENAI_API_KEY}")
            assert config.api_key == "sk-test-123"

    def test_missing_env_var_in_api_key(self) -> None:
        config = ProviderConfig(api_key="${MISSING_KEY}")
        assert config.api_key == ""

    def test_to_provider_info_without_models(self) -> None:
        config = ProviderConfig(base_url="https://api.openai.com/v1")
        info = config.to_provider_info("openai")

        assert isinstance(info, ProviderInfo)
        assert info.id == "openai"
        assert info.name == "Openai"
        assert info.base_url == "https://api.openai.com/v1"
        assert info.models == []

    def test_to_provider_info_with_models(self) -> None:
        model_cfg = ModelConfig(context_window=128000)
        config = ProviderConfig(
            base_url="https://api.openai.com/v1",
            models={"gpt-4o": model_cfg},
        )
        info = config.to_provider_info("openai")

        assert len(info.models) == 1
        assert info.models[0].id == "gpt-4o"
        assert info.models[0].provider_id == "openai"
        assert info.models[0].context_window == 128000


class TestFallbackConfig:
    """Tests for FallbackConfig model."""

    def test_default_values(self) -> None:
        config = FallbackConfig()
        assert config.enabled is False
        assert config.strategy == "sequential"
        assert config.order == []
        assert config.max_attempts == 3
        assert config.retry_on == ["rate_limit", "timeout"]


class TestTimeoutConfig:
    """Tests for TimeoutConfig model."""

    def test_default_values(self) -> None:
        config = TimeoutConfig()
        assert config.connect == 30.0
        assert config.read == 300.0
        assert config.write == 30.0
        assert config.pool == 30.0

    def test_custom_values(self) -> None:
        config = TimeoutConfig(connect=10.0, read=120.0, write=5.0, pool=15.0)
        assert config.connect == 10.0
        assert config.read == 120.0
        assert config.write == 5.0
        assert config.pool == 15.0

    def test_partial_override(self) -> None:
        config = TimeoutConfig(read=60.0)
        assert config.connect == 30.0
        assert config.read == 60.0
        assert config.write == 30.0
        assert config.pool == 30.0

    def test_provider_config_has_timeout(self) -> None:
        """ProviderConfig должен иметь поле timeout."""
        config = ProviderConfig()
        assert isinstance(config.timeout, TimeoutConfig)
        assert config.timeout.read == 300.0

    def test_provider_config_custom_timeout(self) -> None:
        """ProviderConfig должен принимать кастомный timeout."""
        config = ProviderConfig(
            timeout=TimeoutConfig(connect=5.0, read=60.0),
        )
        assert config.timeout.connect == 5.0
        assert config.timeout.read == 60.0
