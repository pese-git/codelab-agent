"""Unit тесты для загрузчика конфигурации Context Manager."""

import os

import pytest

from codelab.server.agent.context.config_loader import load_context_config
from codelab.server.agent.context.models import ContextConfig


class TestLoadContextConfig:
    """Тесты загрузки ContextConfig."""

    def test_defaults_when_no_toml(self):
        """Загрузка без TOML возвращает дефолты."""
        config = load_context_config()

        assert config.enabled is False
        assert config.gather_enabled is True
        assert config.max_context_tokens == 128000

    def test_from_toml_agents_context(self):
        """Загрузка из TOML [agents.context]."""
        toml_data = {
            "agents": {
                "context": {
                    "enabled": True,
                    "max_context_tokens": 64000,
                    "skeletonize": False,
                },
            },
        }

        config = load_context_config(toml_data)

        assert config.enabled is True
        assert config.max_context_tokens == 64000
        assert config.skeletonize is False

    def test_from_toml_context_root(self):
        """Загрузка из TOML [context] (альтернативный путь)."""
        toml_data = {
            "context": {
                "enabled": True,
                "cache_max_files": 500,
            },
        }

        config = load_context_config(toml_data)

        assert config.enabled is True
        assert config.cache_max_files == 500

    def test_env_overrides_toml(self):
        """Env variables переопределяют TOML."""
        toml_data = {
            "agents": {
                "context": {
                    "enabled": False,
                    "max_context_tokens": 64000,
                },
            },
        }

        os.environ["CODELAB_CONTEXT_ENABLED"] = "true"
        os.environ["CODELAB_CONTEXT_MAX_CONTEXT_TOKENS"] = "256000"

        try:
            config = load_context_config(toml_data)

            assert config.enabled is True
            assert config.max_context_tokens == 256000
        finally:
            del os.environ["CODELAB_CONTEXT_ENABLED"]
            del os.environ["CODELAB_CONTEXT_MAX_CONTEXT_TOKENS"]

    def test_env_bool_values(self):
        """Env bool values: true/1/yes → True, остальное → False."""
        os.environ["CODELAB_CONTEXT_ENABLED"] = "1"
        os.environ["CODELAB_CONTEXT_SKELETONIZE"] = "yes"
        os.environ["CODELAB_CONTEXT_FILE_CACHE"] = "false"

        try:
            config = load_context_config()

            assert config.enabled is True
            assert config.skeletonize is True
            assert config.file_cache is False
        finally:
            del os.environ["CODELAB_CONTEXT_ENABLED"]
            del os.environ["CODELAB_CONTEXT_SKELETONIZE"]
            del os.environ["CODELAB_CONTEXT_FILE_CACHE"]

    def test_env_float_values(self):
        """Env float values корректно парсятся."""
        os.environ["CODELAB_CONTEXT_SYSTEM_SHARE"] = "0.30"

        try:
            config = load_context_config()

            assert config.system_share == pytest.approx(0.30)
        finally:
            del os.environ["CODELAB_CONTEXT_SYSTEM_SHARE"]

    def test_env_invalid_int_logged(self):
        """Невалидный int в env логируется и игнорируется."""
        os.environ["CODELAB_CONTEXT_MAX_CONTEXT_TOKENS"] = "not_a_number"

        try:
            config = load_context_config()

            assert config.max_context_tokens == 128000
        finally:
            del os.environ["CODELAB_CONTEXT_MAX_CONTEXT_TOKENS"]


class TestDeprecatedEnableFcm:
    """Тесты депрекейта enable_fcm."""

    def test_enable_fcm_alias_for_enabled(self):
        """enable_fcm работает как алиас на enabled."""
        toml_data = {
            "agents": {
                "context": {
                    "enable_fcm": True,
                },
            },
        }

        config = load_context_config(toml_data)

        assert config.enabled is True

    def test_enabled_takes_precedence_over_enable_fcm(self):
        """enabled имеет приоритет над enable_fcm."""
        toml_data = {
            "agents": {
                "context": {
                    "enabled": False,
                    "enable_fcm": True,
                },
            },
        }

        config = load_context_config(toml_data)

        assert config.enabled is False

    def test_enable_fcm_logs_warning(self, caplog):
        """enable_fcm логирует warning."""
        import logging

        toml_data = {
            "agents": {
                "context": {
                    "enable_fcm": True,
                },
            },
        }

        with caplog.at_level(logging.WARNING):
            load_context_config(toml_data)

        assert any("enable_fcm" in record.message for record in caplog.records)
        assert any("deprecated" in record.message for record in caplog.records)
