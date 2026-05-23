"""Integration tests for TOML config -> Registry -> configOptions flow."""

from __future__ import annotations

import tempfile
from pathlib import Path

from codelab.server.config import AppConfig
from codelab.server.di import RegistryProvider
from codelab.server.protocol.handlers.config_option_builder import ConfigOptionBuilder
from codelab.server.protocol.handlers.session import build_config_options


class TestRegistryToConfigOptionsFlow:
    """Integration tests for full flow: TOML → Registry → configOptions."""

    def test_registry_list_all_models_returns_toml_models(self) -> None:
        """registry.list_all_models() возвращает модели из TOML."""
        provider = RegistryProvider()
        registry = provider.get_llm_registry(AppConfig())

        models = registry.list_all_models()

        # Должны быть модели из codelab.toml.example
        assert len(models) > 0

        # Проверим что есть модели от разных провайдеров
        provider_ids = {m.provider_id for m in models}
        assert "openai" in provider_ids
        assert "anthropic" in provider_ids

    def test_config_options_model_contains_all_toml_models(self) -> None:
        """configOptions.model.options содержит все модели из TOML."""
        provider = RegistryProvider()
        registry = provider.get_llm_registry(AppConfig())
        builder = ConfigOptionBuilder(registry)

        model_option = builder.build_model_config_option()

        assert model_option["id"] == "model"
        assert model_option["category"] == "model"
        assert len(model_option["options"]) > 0

        # Проверим формат options
        for opt in model_option["options"]:
            assert "value" in opt
            assert "label" in opt
            # value должен быть в формате provider/model
            assert "/" in opt["value"]

    def test_config_options_format_matches_acp_spec(self) -> None:
        """Формат configOptions соответствует ACP spec."""
        provider = RegistryProvider()
        registry = provider.get_llm_registry(AppConfig())
        builder = ConfigOptionBuilder(registry)

        model_spec = builder.build_model_config_option()
        config_specs = {"model": model_spec}
        config_values = {"model": "openai/gpt-4o"}

        config_options = build_config_options(config_values, config_specs)

        assert len(config_options) == 1
        model_opt = config_options[0]

        # Проверим структуру согласно ACP spec
        assert model_opt["id"] == "model"
        assert model_opt["name"] == "Model"
        assert model_opt["category"] == "model"
        assert model_opt["type"] == "select"
        assert model_opt["currentValue"] == "openai/gpt-4o"
        assert isinstance(model_opt["options"], list)
        assert len(model_opt["options"]) > 0

        # Проверим формат каждого option
        for opt in model_opt["options"]:
            assert "value" in opt
            assert "label" in opt

    def test_backward_compatibility_empty_toml(self) -> None:
        """Пустой TOML → пустой список моделей → fallback на defaults."""
        # Создаём временный пустой TOML
        toml_content = """
[llm]
provider = "mock"
model = "mock-model"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            toml_path = f.name

        try:
            # temporarily change cwd to test
            import os

            old_cwd = os.getcwd()
            os.chdir(Path(toml_path).parent)

            # Создаём symlink to our temp toml as codelab.toml
            Path("codelab.toml").symlink_to(Path(toml_path).name)

            try:
                provider = RegistryProvider()
                registry = provider.get_llm_registry(AppConfig())

                # Registry должен иметь только mock
                assert "mock" in registry.get_registered_providers()

                # Mock не имеет моделей в TOML
                mock_models = [m for m in registry.list_all_models() if m.provider_id == "mock"]
                assert len(mock_models) == 0
            finally:
                Path("codelab.toml").unlink(missing_ok=True)
                os.chdir(old_cwd)
        finally:
            Path(toml_path).unlink()
