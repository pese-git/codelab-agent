"""Дополнительные тесты для покрытия непокрытых участков server/config.py."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from codelab.server.config import AppConfig, LLMConfig, _get_env, _get_env_typed
from codelab.server.toml_config.pydantic_config import FallbackConfig, ProviderConfig


class TestEnvHelpers:
    """Тесты вспомогательных функций чтения переменных окружения."""

    def test_get_env_returns_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_get_env возвращает значение установленной переменной окружения."""
        monkeypatch.setenv("TEST_CODELAB_VAR", "value")

        result = _get_env("TEST_CODELAB_VAR")

        assert result == "value"

    def test_get_env_returns_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_get_env возвращает default если переменная не установлена."""
        monkeypatch.delenv("MISSING_CODELAB_VAR", raising=False)

        result = _get_env("MISSING_CODELAB_VAR", "default")

        assert result == "default"

    def test_get_env_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_get_env возвращает None если переменная не установлена и default не задан."""
        monkeypatch.delenv("MISSING_CODELAB_VAR", raising=False)

        result = _get_env("MISSING_CODELAB_VAR")

        assert result is None

    def test_get_env_typed_converts_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_get_env_typed приводит значение переменной к указанному типу."""
        monkeypatch.setenv("TEST_CODELAB_INT", "42")

        result = _get_env_typed("TEST_CODELAB_INT", "0", int)

        assert result == 42
        assert isinstance(result, int)

    def test_get_env_typed_returns_default_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_get_env_typed возвращает default если переменная не установлена."""
        monkeypatch.delenv("MISSING_CODELAB_VAR", raising=False)

        result = _get_env_typed("MISSING_CODELAB_VAR", "default", str)

        assert result == "default"

    def test_get_env_typed_converts_float(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_get_env_typed корректно приводит значение к float."""
        monkeypatch.setenv("TEST_CODELAB_FLOAT", "3.14")

        result = _get_env_typed("TEST_CODELAB_FLOAT", "0.0", float)

        assert result == pytest.approx(3.14)


class TestLLMConfigFromValues:
    """Тесты фабричного метода LLMConfig.from_values."""

    def test_from_values_overrides_defaults(self) -> None:
        """from_values позволяет переопределить поля по умолчанию."""
        config = LLMConfig.from_values(
            provider="openai",
            model="gpt-3.5",
            temperature=0.5,
            max_tokens=1024,
        )

        assert config.provider == "openai"
        assert config.model == "gpt-3.5"
        assert config.temperature == 0.5
        assert config.max_tokens == 1024

    def test_from_values_preserves_unset_defaults(self) -> None:
        """from_values сохраняет значения по умолчанию для непереданных полей."""
        config = LLMConfig.from_values(provider="anthropic")

        assert config.provider == "anthropic"
        assert config.model == "gpt-4o"
        assert config.api_key is None


class TestLoadMergedTomlData:
    """Тесты загрузки и слияния TOML-данных."""

    def test_invalid_toml_is_ignored(self, tmp_path: Path) -> None:
        """_load_merged_toml_data игнорирует файлы с некорректным TOML."""
        invalid = tmp_path / "invalid.toml"
        invalid.write_text("this is not valid toml [[[")

        result = AppConfig._load_merged_toml_data([invalid])

        assert result == {}

    def test_missing_file_is_ignored(self, tmp_path: Path) -> None:
        """_load_merged_toml_data игнорирует несуществующие файлы."""
        missing = tmp_path / "missing.toml"

        result = AppConfig._load_merged_toml_data([missing])

        assert result == {}

    def test_valid_file_still_merged_with_invalid(
        self, tmp_path: Path
    ) -> None:
        """Корректные файлы объединяются даже если в списке есть некорректные."""
        valid = tmp_path / "valid.toml"
        valid.write_text("[llm]\nprovider = 'openai'\n")
        invalid = tmp_path / "invalid.toml"
        invalid.write_text("not valid [[")

        result = AppConfig._load_merged_toml_data([valid, invalid])

        assert result["llm"]["provider"] == "openai"


class TestLLMTimeoutFromToml:
    """Тесты чтения таймаутов из TOML-секции [llm.timeout]."""

    def test_timeout_section_overrides_defaults(self, tmp_path: Path) -> None:
        """[llm.timeout] переопределяет дефолтные таймауты."""
        (tmp_path / "codelab.toml").write_text(
            "[llm]\nprovider = 'openai'\n"
            "[llm.timeout]\nconnect = 5.0\nread = 60.0\n"
            "write = 10.0\npool = 15.0\n"
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                empty_home = tmp_path / "empty_home"
                empty_home.mkdir()
                with patch.object(Path, "home", return_value=empty_home):
                    config = AppConfig.load()

        finally:
            os.chdir(old_cwd)

        assert config.llm.timeout.connect == 5.0
        assert config.llm.timeout.read == 60.0
        assert config.llm.timeout.write == 10.0
        assert config.llm.timeout.pool == 15.0


class TestInvalidEnvTimeout:
    """Тесты обработки некорректных значений таймаутов из env."""

    def test_invalid_timeout_read_uses_default(self, tmp_path: Path) -> None:
        """Некорректное CODELAB_LLM_TIMEOUT_READ не ломает загрузку и использует default."""
        (tmp_path / "codelab.toml").write_text("[llm]\nprovider = 'openai'\n")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            env = {"CODELAB_LLM_TIMEOUT_READ": "not-a-number"}
            with patch.dict(os.environ, env, clear=True):
                empty_home = tmp_path / "empty_home"
                empty_home.mkdir()
                with patch.object(Path, "home", return_value=empty_home):
                    config = AppConfig.load()
        finally:
            os.chdir(old_cwd)

        assert config.llm.timeout.read == 300.0

    def test_invalid_timeout_connect_uses_default(self, tmp_path: Path) -> None:
        """Некорректное CODELAB_LLM_TIMEOUT_CONNECT не ломает загрузку и использует default."""
        (tmp_path / "codelab.toml").write_text("[llm]\nprovider = 'openai'\n")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            env = {"CODELAB_LLM_TIMEOUT_CONNECT": "bad-value"}
            with patch.dict(os.environ, env, clear=True):
                empty_home = tmp_path / "empty_home"
                empty_home.mkdir()
                with patch.object(Path, "home", return_value=empty_home):
                    config = AppConfig.load()
        finally:
            os.chdir(old_cwd)

        assert config.llm.timeout.connect == 30.0


class TestNonDictNestedConfigs:
    """Тесты ситуаций, когда секции конфига имеют некорректный тип."""

    def test_fallback_non_dict_uses_default(self, tmp_path: Path) -> None:
        """Если llm.fallback в TOML не dict, используется FallbackConfig по умолчанию."""
        (tmp_path / "codelab.toml").write_text(
            "[llm]\nprovider = 'openai'\nfallback = 'enabled'\n"
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                empty_home = tmp_path / "empty_home"
                empty_home.mkdir()
                with patch.object(Path, "home", return_value=empty_home):
                    config = AppConfig.load()
        finally:
            os.chdir(old_cwd)

        assert isinstance(config.llm.fallback, FallbackConfig)
        assert config.llm.fallback.enabled is False

    def test_observability_non_dict_uses_default(self, tmp_path: Path) -> None:
        """Если observability в TOML не dict, используется ObservabilityConfig по умолчанию."""
        (tmp_path / "codelab.toml").write_text(
            "observability = 'enabled'\n"
            "[llm]\nprovider = 'openai'\n"
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                empty_home = tmp_path / "empty_home"
                empty_home.mkdir()
                with patch.object(Path, "home", return_value=empty_home):
                    config = AppConfig.load()
        finally:
            os.chdir(old_cwd)

        assert config.observability.enabled is True
        assert config.observability.export_dir == "~/.codelab/data/observability"

    def test_agents_non_dict_uses_default(self, tmp_path: Path) -> None:
        """Если agents в TOML не dict, используется AgentsConfig по умолчанию."""
        (tmp_path / "codelab.toml").write_text(
            "agents = 'multi'\n"
            "[llm]\nprovider = 'openai'\n"
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                empty_home = tmp_path / "empty_home"
                empty_home.mkdir()
                with patch.object(Path, "home", return_value=empty_home):
                    config = AppConfig.load()
        finally:
            os.chdir(old_cwd)

        assert config.agents.strategy == "single"
        assert config.agents.max_steps == 7


class TestNoTomlPathBranches:
    """Тесты веток load() при отсутствии TOML-файлов."""

    def test_no_toml_path_processes_providers_and_fallback(
        self, tmp_path: Path
    ) -> None:
        """При отсутствии TOML providers и fallback обрабатываются корректно."""
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(
                    AppConfig, "_find_toml_files", return_value=[]
                ):
                    merged = {
                        "provider": "mock",
                        "model": "gpt-4o",
                        "temperature": 0.7,
                        "max_tokens": 8192,
                        "api_key": None,
                        "base_url": None,
                        "providers": {
                            "openai": {"api_key": "sk-patched", "base_url": "http://test"}
                        },
                        "fallback": "not-a-dict",
                    }
                    with patch.object(
                        AppConfig, "_merge_llm_config", return_value=merged
                    ):
                        config = AppConfig.load()
        finally:
            os.chdir(old_cwd)

        assert "openai" in config.llm.providers
        assert config.llm.providers["openai"].api_key == "sk-patched"
        assert isinstance(config.llm.providers["openai"], ProviderConfig)
        assert isinstance(config.llm.fallback, FallbackConfig)
        assert config.llm.fallback.enabled is False
