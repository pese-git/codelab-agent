"""Unit tests for Pydantic TOML configuration models."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from codelab.server.llm.models import ModelInfo, ProviderInfo
from codelab.server.toml_config.pydantic_config import (
    FallbackConfig,
    LLMSectionConfig,
    ModelConfig,
    ProviderConfig,
    TOMLConfig,
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


class TestLLMSectionConfig:
    """Tests for LLMSectionConfig model."""

    def test_default_values(self) -> None:
        config = LLMSectionConfig()
        assert config.provider == "mock"
        assert config.model == "mock-model"
        assert config.temperature == 0.7
        assert config.max_tokens == 8192
        assert config.providers == {}
        assert isinstance(config.fallback, FallbackConfig)


class TestTOMLConfig:
    """Tests for TOMLConfig model."""

    def test_default_values(self) -> None:
        config = TOMLConfig()
        assert config.llm_provider == "mock"
        assert config.llm_model == "mock-model"
        assert config.temperature == 0.7
        assert config.max_tokens == 8192
        assert config.providers == {}
        assert isinstance(config.fallback, FallbackConfig)

    def test_from_toml_file_not_exists(self) -> None:
        config = TOMLConfig.from_toml_file("/nonexistent/path/file.toml")
        assert config.llm_provider == "mock"
        assert config.providers == {}

    def test_from_toml_file_with_full_config(self) -> None:
        toml_content = """
[llm]
provider = "openai"
model = "openai/gpt-4o"
temperature = 0.8
max_tokens = 4096

[llm.providers.openai]
api_key = "${OPENAI_API_KEY}"
base_url = "https://api.openai.com/v1"
default_model = "gpt-4o"

[llm.providers.openai.models.gpt-4o]
context_window = 128000
max_output_tokens = 16384

[llm.providers.openai.models.o3]
context_window = 200000

[llm.providers.anthropic]
base_url = "https://api.anthropic.com"

[llm.providers.anthropic.models.claude-sonnet-4]
context_window = 200000
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            toml_path = f.name

        try:
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
                config = TOMLConfig.from_toml_file(Path(toml_path))

            # Check LLM section
            assert config.llm_provider == "openai"
            assert config.llm_model == "openai/gpt-4o"
            assert config.temperature == 0.8
            assert config.max_tokens == 4096

            # Check providers
            assert "openai" in config.providers
            assert "anthropic" in config.providers

            # Check OpenAI provider
            openai_cfg = config.providers["openai"]
            assert openai_cfg.api_key == "sk-test"
            assert openai_cfg.base_url == "https://api.openai.com/v1"
            assert "gpt-4o" in openai_cfg.models
            assert "o3" in openai_cfg.models
            assert openai_cfg.models["gpt-4o"].context_window == 128000

            # Check Anthropic provider
            anthropic_cfg = config.providers["anthropic"]
            assert "claude-sonnet-4" in anthropic_cfg.models
        finally:
            Path(toml_path).unlink()

    def test_from_toml_file_empty_providers(self) -> None:
        toml_content = """
[llm]
provider = "mock"
model = "mock-model"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            toml_path = f.name

        try:
            config = TOMLConfig.from_toml_file(Path(toml_path))
            assert config.providers == {}
        finally:
            Path(toml_path).unlink()

    def test_from_toml_file_provider_without_models(self) -> None:
        toml_content = """
[llm]
provider = "openai"

[llm.providers.openai]
base_url = "https://api.openai.com/v1"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            toml_path = f.name

        try:
            config = TOMLConfig.from_toml_file(Path(toml_path))
            assert "openai" in config.providers
            assert config.providers["openai"].models == {}
        finally:
            Path(toml_path).unlink()


class TestTOMLConfigIntegration:
    """Integration tests for TOMLConfig with Registry."""

    def test_to_provider_info_generates_all_models(self) -> None:
        toml_content = """
[llm]
provider = "openai"

[llm.providers.openai]
base_url = "https://api.openai.com/v1"

[llm.providers.openai.models.gpt-4o]
context_window = 128000

[llm.providers.openai.models.o3]
context_window = 200000

[llm.providers.anthropic]
base_url = "https://api.anthropic.com"

[llm.providers.anthropic.models.claude-sonnet-4]
context_window = 200000

[llm.providers.anthropic.models.claude-opus-4]
context_window = 200000
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            toml_path = f.name

        try:
            config = TOMLConfig.from_toml_file(Path(toml_path))

            # Test OpenAI provider info
            openai_info = config.providers["openai"].to_provider_info("openai")
            assert len(openai_info.models) == 2
            assert openai_info.models[0].full_id == "openai/gpt-4o"
            assert openai_info.models[1].full_id == "openai/o3"

            # Test Anthropic provider info
            anthropic_info = config.providers["anthropic"].to_provider_info("anthropic")
            assert len(anthropic_info.models) == 2
            assert anthropic_info.models[0].full_id == "anthropic/claude-sonnet-4"
            assert anthropic_info.models[1].full_id == "anthropic/claude-opus-4"
        finally:
            Path(toml_path).unlink()
