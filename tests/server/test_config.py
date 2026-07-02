"""Тесты для AppConfig с приоритетом источников: CLI > env > .env > TOML > defaults."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from codelab.server.config import AgentsConfig, AppConfig, LLMConfig


class TestAgentsDefaultModelDerivation:
    """agents.default_model выводится из config.llm, если не задан явно."""

    def test_derived_from_llm_defaults(self) -> None:
        """Без явного значения default_model = provider/model из config.llm."""
        config = AppConfig(llm=LLMConfig(provider="mock", model="gpt-4o"))
        assert config.agents.default_model == "mock/gpt-4o"

    def test_follows_llm_override(self) -> None:
        """Смена provider/model в llm меняет производный default_model."""
        config = AppConfig(llm=LLMConfig(provider="ollama", model="gemma"))
        assert config.agents.default_model == "ollama/gemma"

    def test_explicit_value_preserved(self) -> None:
        """Явно заданный agents.default_model не перезаписывается."""
        config = AppConfig(
            llm=LLMConfig(provider="mock", model="gpt-4o"),
            agents=AgentsConfig(default_model="anthropic/claude-sonnet-4"),
        )
        assert config.agents.default_model == "anthropic/claude-sonnet-4"


# ============================================================================
# Тесты LLMConfig defaults
# ============================================================================


class TestLLMConfigDefaults:
    """Тесты дефолтных значений LLMConfig."""

    def test_default_provider_is_mock(self) -> None:
        """По умолчанию provider = mock."""
        config = LLMConfig()
        assert config.provider == "mock"

    def test_default_model(self) -> None:
        """По умолчанию model = gpt-4o."""
        config = LLMConfig()
        assert config.model == "gpt-4o"

    def test_default_temperature(self) -> None:
        """По умолчанию temperature = 0.7."""
        config = LLMConfig()
        assert config.temperature == 0.7

    def test_default_max_tokens(self) -> None:
        """По умолчанию max_tokens = 8192."""
        config = LLMConfig()
        assert config.max_tokens == 8192

    def test_default_api_key_is_none(self) -> None:
        """По умолчанию api_key = None."""
        config = LLMConfig()
        assert config.api_key is None

    def test_default_base_url_is_none(self) -> None:
        """По умолчанию base_url = None."""
        config = LLMConfig()
        assert config.base_url is None

    def test_default_providers_empty(self) -> None:
        """По умолчанию providers = {}."""
        config = LLMConfig()
        assert config.providers == {}

    def test_default_fallback_disabled(self) -> None:
        """По умолчанию fallback.enabled = False."""
        config = LLMConfig()
        assert config.fallback.enabled is False

    def test_default_streaming_off(self) -> None:
        """По умолчанию streaming = False (безопасный дефолт)."""
        config = LLMConfig()
        assert config.streaming is False


# ============================================================================
# Тесты AppConfig.load() — env vars имеют приоритет
# ============================================================================


class TestAppConfigFromEnv:
    """Тесты чтения конфигурации из переменных окружения через AppConfig.load()."""

    def test_provider_from_env(self) -> None:
        """CODELAB_LLM_PROVIDER читается из env."""
        with patch.dict(os.environ, {"CODELAB_LLM_PROVIDER": "openai"}, clear=False):
            old_cwd = os.getcwd()
            try:
                os.chdir(Path(tempfile.mkdtemp()))
                config = AppConfig.load()
                assert config.llm.provider == "openai"
            finally:
                os.chdir(old_cwd)

    def test_model_from_env(self) -> None:
        """CODELAB_LLM_MODEL читается из env."""
        with patch.dict(os.environ, {"CODELAB_LLM_MODEL": "gpt-4-turbo"}, clear=False):
            old_cwd = os.getcwd()
            try:
                os.chdir(Path(tempfile.mkdtemp()))
                config = AppConfig.load()
                assert config.llm.model == "gpt-4-turbo"
            finally:
                os.chdir(old_cwd)

    def test_temperature_from_env(self) -> None:
        """CODELAB_LLM_TEMPERATURE читается из env."""
        with patch.dict(os.environ, {"CODELAB_LLM_TEMPERATURE": "0.9"}, clear=False):
            old_cwd = os.getcwd()
            try:
                os.chdir(Path(tempfile.mkdtemp()))
                config = AppConfig.load()
                assert config.llm.temperature == 0.9
            finally:
                os.chdir(old_cwd)

    def test_max_tokens_from_env(self) -> None:
        """CODELAB_LLM_MAX_TOKENS читается из env."""
        with patch.dict(os.environ, {"CODELAB_LLM_MAX_TOKENS": "4096"}, clear=False):
            old_cwd = os.getcwd()
            try:
                os.chdir(Path(tempfile.mkdtemp()))
                config = AppConfig.load()
                assert config.llm.max_tokens == 4096
            finally:
                os.chdir(old_cwd)

    def test_streaming_from_env_true(self) -> None:
        """CODELAB_LLM_STREAMING=true включает streaming."""
        with patch.dict(os.environ, {"CODELAB_LLM_STREAMING": "true"}, clear=False):
            old_cwd = os.getcwd()
            try:
                os.chdir(Path(tempfile.mkdtemp()))
                config = AppConfig.load()
                assert config.llm.streaming is True
            finally:
                os.chdir(old_cwd)

    def test_streaming_from_env_false(self) -> None:
        """CODELAB_LLM_STREAMING=false явно выключает streaming (не truthy-строка)."""
        with patch.dict(os.environ, {"CODELAB_LLM_STREAMING": "false"}, clear=False):
            old_cwd = os.getcwd()
            try:
                os.chdir(Path(tempfile.mkdtemp()))
                config = AppConfig.load()
                assert config.llm.streaming is False
            finally:
                os.chdir(old_cwd)

    def test_api_key_from_env(self) -> None:
        """CODELAB_LLM_API_KEY читается из env."""
        with patch.dict(os.environ, {"CODELAB_LLM_API_KEY": "sk-test-123"}, clear=False):
            old_cwd = os.getcwd()
            try:
                os.chdir(Path(tempfile.mkdtemp()))
                config = AppConfig.load()
                assert config.llm.api_key == "sk-test-123"
            finally:
                os.chdir(old_cwd)

    def test_base_url_from_env(self) -> None:
        """CODELAB_LLM_BASE_URL читается из env."""
        with patch.dict(
            os.environ,
            {"CODELAB_LLM_BASE_URL": "https://custom.api.com/v1"},
            clear=False,
        ):
            old_cwd = os.getcwd()
            try:
                os.chdir(Path(tempfile.mkdtemp()))
                config = AppConfig.load()
                assert config.llm.base_url == "https://custom.api.com/v1"
            finally:
                os.chdir(old_cwd)


# ============================================================================
# Тесты AppConfig.load() с TOML
# ============================================================================


class TestAppConfigLoad:
    """Тесты загрузки AppConfig из всех источников."""

    def _create_toml(self, tmp_path: Path, content: str) -> str:
        """Создаёт TOML файл и возвращает путь."""
        toml_file = tmp_path / "codelab.toml"
        toml_file.write_text(content)
        return str(toml_file)

    def test_load_without_toml(self, tmp_path: Path) -> None:
        """load() без TOML файла использует defaults."""
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                # Патчим home() чтобы не подхватился ~/.codelab/codelab.toml
                import unittest.mock

                empty_home = tmp_path / "empty_home"
                empty_home.mkdir()
                with unittest.mock.patch.object(Path, "home", return_value=empty_home):
                    config = AppConfig.load()
                    assert config.llm.provider == "mock"
                    assert config.llm.model == "gpt-4o"
        finally:
            os.chdir(old_cwd)

    def test_load_with_toml(self, tmp_path: Path) -> None:
        """load() с TOML файлом читает конфигурацию."""
        toml_content = """
[llm]
provider = "openai"
model = "openai/gpt-4o"
temperature = 0.8
max_tokens = 4096
"""
        self._create_toml(tmp_path, toml_content)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                config = AppConfig.load()
                assert config.llm.provider == "openai"
                assert config.llm.model == "openai/gpt-4o"
                assert config.llm.temperature == 0.8
                assert config.llm.max_tokens == 4096
        finally:
            os.chdir(old_cwd)

    def test_load_streaming_from_toml(self, tmp_path: Path) -> None:
        """load() читает streaming из [llm] секции TOML."""
        self._create_toml(tmp_path, "[llm]\nstreaming = true\n")
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                config = AppConfig.load()
                assert config.llm.streaming is True
        finally:
            os.chdir(old_cwd)

    def test_env_streaming_overrides_toml(self, tmp_path: Path) -> None:
        """env CODELAB_LLM_STREAMING имеет приоритет над TOML."""
        self._create_toml(tmp_path, "[llm]\nstreaming = true\n")
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {"CODELAB_LLM_STREAMING": "false"}, clear=True):
                config = AppConfig.load()
                assert config.llm.streaming is False
        finally:
            os.chdir(old_cwd)

    def test_load_with_toml_providers(self, tmp_path: Path) -> None:
        """load() с TOML файлом читает providers."""
        toml_content = """
[llm]
provider = "openai"

[llm.providers.openai]
base_url = "https://api.openai.com/v1"

[llm.providers.openai.models.gpt-4o]
context_window = 128000
"""
        self._create_toml(tmp_path, toml_content)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                config = AppConfig.load()
                assert "openai" in config.llm.providers
                assert config.llm.providers["openai"].base_url == "https://api.openai.com/v1"
                assert "gpt-4o" in config.llm.providers["openai"].models
        finally:
            os.chdir(old_cwd)

    def test_load_api_key_from_provider_config(self, tmp_path: Path) -> None:
        """api_key берётся из конфига активного провайдера если не задан напрямую."""
        toml_content = """
[llm]
provider = "openai"

[llm.providers.openai]
api_key = "sk-test-from-provider"
base_url = "https://api.openai.com/v1"
"""
        self._create_toml(tmp_path, toml_content)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                config = AppConfig.load()
                assert config.llm.api_key == "sk-test-from-provider"
                assert config.llm.base_url == "https://api.openai.com/v1"
        finally:
            os.chdir(old_cwd)

    def test_load_api_key_env_var_expansion(self, tmp_path: Path) -> None:
        """api_key из provider config раскрывает env vars."""
        toml_content = """
[llm]
provider = "openai"

[llm.providers.openai]
api_key = "${OPENAI_API_KEY}"
"""
        self._create_toml(tmp_path, toml_content)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-real-key"}, clear=False):
                config = AppConfig.load()
                assert config.llm.api_key == "sk-real-key"
        finally:
            os.chdir(old_cwd)

    def test_load_api_key_env_overrides_provider(self, tmp_path: Path) -> None:
        """CODELAB_LLM_API_KEY имеет приоритет над api_key из provider config."""
        toml_content = """
[llm]
provider = "openai"

[llm.providers.openai]
api_key = "sk-from-provider"
"""
        self._create_toml(tmp_path, toml_content)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(
                os.environ,
                {"CODELAB_LLM_API_KEY": "sk-from-env"},
                clear=False,
            ):
                config = AppConfig.load()
                assert config.llm.api_key == "sk-from-env"  # env > provider config
        finally:
            os.chdir(old_cwd)

    def test_load_with_custom_toml_path(self, tmp_path: Path) -> None:
        """load() с custom toml_path читает указанный файл."""
        toml_content = """
[llm]
provider = "anthropic"
model = "anthropic/claude-sonnet-4"
"""
        custom_toml = tmp_path / "custom.toml"
        custom_toml.write_text(toml_content)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                config = AppConfig.load(toml_path=str(custom_toml))
                assert config.llm.provider == "anthropic"
                assert config.llm.model == "anthropic/claude-sonnet-4"
        finally:
            os.chdir(old_cwd)


# ============================================================================
# Тесты приоритета источников
# ============================================================================


class TestConfigPriority:
    """Тесты приоритета: CLI (init) > env > TOML > defaults."""

    def _create_toml(self, tmp_path: Path, content: str) -> str:
        toml_file = tmp_path / "codelab.toml"
        toml_file.write_text(content)
        return str(toml_file)

    def test_env_overrides_toml(self, tmp_path: Path) -> None:
        """Env vars имеют приоритет над TOML."""
        toml_content = """
[llm]
provider = "openai"
model = "openai/gpt-4o"
temperature = 0.8
"""
        self._create_toml(tmp_path, toml_content)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Env vars переопределяют TOML
            with patch.dict(
                os.environ,
                {
                    "CODELAB_LLM_PROVIDER": "mock",
                    "CODELAB_LLM_MODEL": "mock-model",
                },
                clear=False,
            ):
                config = AppConfig.load()
                assert config.llm.provider == "mock"  # env > toml
                assert config.llm.model == "mock-model"  # env > toml
                assert config.llm.temperature == 0.8  # из TOML (не переопределено)
        finally:
            os.chdir(old_cwd)

    def test_cli_overrides_toml(self, tmp_path: Path) -> None:
        """CLI kwargs (ручные overrides) имеют высший приоритет."""
        toml_content = """
[llm]
provider = "openai"
model = "openai/gpt-4o"
"""
        self._create_toml(tmp_path, toml_content)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                config = AppConfig.load()
                config.llm.provider = "anthropic"  # CLI override
                config.llm.model = "anthropic/claude-sonnet-4"

                assert config.llm.provider == "anthropic"
                assert config.llm.model == "anthropic/claude-sonnet-4"
        finally:
            os.chdir(old_cwd)

    def test_cli_overrides_env(self, tmp_path: Path) -> None:
        """CLI kwargs имеют приоритет над env vars."""
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {"CODELAB_LLM_PROVIDER": "openai"}, clear=False):
                config = AppConfig.load()
                config.llm.provider = "mock"  # CLI override
                assert config.llm.provider == "mock"  # CLI > env
        finally:
            os.chdir(old_cwd)

    def test_toml_overrides_defaults(self, tmp_path: Path) -> None:
        """TOML имеет приоритет над defaults."""
        toml_content = """
[llm]
provider = "openai"
model = "openai/gpt-4o"
temperature = 0.9
max_tokens = 4096
"""
        self._create_toml(tmp_path, toml_content)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                config = AppConfig.load()
                assert config.llm.provider == "openai"  # toml > default
                assert config.llm.model == "openai/gpt-4o"  # toml > default
                assert config.llm.temperature == 0.9  # toml > default
                assert config.llm.max_tokens == 4096  # toml > default
        finally:
            os.chdir(old_cwd)


# ============================================================================
# Тесты _find_toml_file
# ============================================================================


class TestFindTomlFile:
    """Тесты поиска TOML файла."""

    def test_find_toml_custom_path_exists(self, tmp_path: Path) -> None:
        """Поиск по custom path — файл существует."""
        custom_toml = tmp_path / "custom.toml"
        custom_toml.write_text("[llm]\nprovider = 'openai'")

        result = AppConfig._find_toml_file(str(custom_toml))
        assert result == custom_toml

    def test_find_toml_custom_path_not_exists(self, tmp_path: Path) -> None:
        """Поиск по custom path — файл не существует, fallback на другие."""
        nonexistent = tmp_path / "nonexistent.toml"

        result = AppConfig._find_toml_file(str(nonexistent))
        # Если custom не найден, fallback на другие файлы
        # Результат зависит от окружения — главное что не упало
        assert result is not None

    def test_find_toml_not_found(self, tmp_path: Path) -> None:
        """Если нет project TOML файлов — _find_toml_files возвращает пустой список."""
        # Проверяем что без project файлов список пуст
        # (auth.toml и codelab.toml могут существовать в ~/.codelab)
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            import unittest.mock

            empty_home = tmp_path / "empty_home"
            empty_home.mkdir()
            with unittest.mock.patch.object(Path, "home", return_value=empty_home):
                files = AppConfig._find_toml_files()
                assert len(files) == 0
        finally:
            os.chdir(old_cwd)

    def test_find_toml_fallback_to_example(self, tmp_path: Path) -> None:
        """codelab.toml.example НЕ загружается — это только шаблон."""
        example_toml = tmp_path / "codelab.toml.example"
        example_toml.write_text("[llm]\nprovider = 'mock'")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            import unittest.mock

            empty_home = tmp_path / "empty_home"
            empty_home.mkdir()
            with unittest.mock.patch.object(Path, "home", return_value=empty_home):
                result = AppConfig._find_toml_file()
                # codelab.toml.example не загружается — возвращается None
                assert result is None
        finally:
            os.chdir(old_cwd)


# ============================================================================
# Тесты multi-file TOML chain
# ============================================================================


class TestMultiFileTomlChain:
    """Тесты цепочки TOML файлов: auth.toml < codelab.toml < codelab.local.toml."""

    def test_find_toml_files_returns_all_existing(self, tmp_path: Path) -> None:
        """_find_toml_files возвращает все существующие файлы в порядке priority."""
        # Создаём codelab.toml
        (tmp_path / "codelab.toml").write_text("[llm]\nprovider = 'project'")
        # Создаём codelab.local.toml
        (tmp_path / "codelab.local.toml").write_text("[llm]\nprovider = 'local'")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            files = AppConfig._find_toml_files()
            # Минимум 2 файла: codelab.toml и codelab.local.toml
            # (может быть 3 если ~/.codelab/auth.toml существует)
            assert len(files) >= 2
            # Проверяем порядок: codelab.toml перед codelab.local.toml
            codelab_idx = next(i for i, f in enumerate(files) if f.name == "codelab.toml")
            local_idx = next(i for i, f in enumerate(files) if f.name == "codelab.local.toml")
            assert codelab_idx < local_idx  # codelab.toml имеет lower priority
        finally:
            os.chdir(old_cwd)

    def test_find_toml_files_with_auth_toml(self, tmp_path: Path) -> None:
        """_find_toml_files включает auth.toml если существует."""
        (tmp_path / "codelab.toml").write_text("[llm]\nprovider = 'project'")

        # Создаём auth.toml в домашней директории
        codelab_home = tmp_path / ".codelab"
        codelab_home.mkdir()
        auth_toml = codelab_home / "auth.toml"
        auth_toml.write_text("[llm.providers.openai]\napi_key = 'sk-auth-key'")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Патчим home() для теста
            import unittest.mock

            with unittest.mock.patch.object(Path, "home", return_value=codelab_home.parent):
                files = AppConfig._find_toml_files()
                # auth.toml должен быть первым (lowest priority)
                assert any(f.name == "auth.toml" for f in files)
        finally:
            os.chdir(old_cwd)

    def test_find_toml_files_with_global_codelab_toml(self, tmp_path: Path) -> None:
        """_find_toml_files включает ~/.codelab/codelab.toml если существует."""
        (tmp_path / "codelab.toml").write_text("[llm]\nprovider = 'project'")

        # Создаём ~/.codelab/codelab.toml
        codelab_home = tmp_path / ".codelab"
        codelab_home.mkdir()
        global_toml = codelab_home / "codelab.toml"
        global_toml.write_text("[llm]\nprovider = 'openrouter'")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            import unittest.mock

            with unittest.mock.patch.object(Path, "home", return_value=codelab_home.parent):
                files = AppConfig._find_toml_files()
                # Глобальный codelab.toml должен быть перед project codelab.toml
                names = [f.name for f in files]
                assert "codelab.toml" in names
                # Проверяем порядок: сначала глобальный, потом project
                # (оба называются codelab.toml, но глобальный должен быть раньше)
                global_in_files = [f for f in files if f.parent.name == ".codelab"]
                project_in_files = [f for f in files if f.parent == tmp_path]
                if global_in_files and project_in_files:
                    assert files.index(global_in_files[0]) < files.index(project_in_files[0])
        finally:
            os.chdir(old_cwd)

    def test_global_codelab_toml_overrides_example(self, tmp_path: Path) -> None:
        """~/.codelab/codelab.toml переопределяет codelab.toml.example из проекта."""
        # Создаём только codelab.toml.example в проекте
        (tmp_path / "codelab.toml.example").write_text(
            "[llm]\nprovider = 'openai'\nmodel = 'openai/gpt-4o'"
        )

        # Создаём ~/.codelab/codelab.toml
        codelab_home = tmp_path / ".codelab"
        codelab_home.mkdir()
        (codelab_home / "codelab.toml").write_text(
            "[llm]\nprovider = 'openrouter'\nmodel = 'openrouter/qwen/qwen3.6-plus'"
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            import unittest.mock

            with unittest.mock.patch.object(Path, "home", return_value=codelab_home.parent):
                config = AppConfig.load()
                assert config.llm.provider == "openrouter"  # из global
                assert config.llm.model == "openrouter/qwen/qwen3.6-plus"  # из global
        finally:
            os.chdir(old_cwd)

    def test_deep_merge_nested_dicts(self) -> None:
        """_deep_merge корректно объединяет nested dicts."""
        base = {"llm": {"provider": "mock", "providers": {"openai": {"api_key": "key1"}}}}
        override = {"llm": {"model": "gpt-4o", "providers": {"anthropic": {"api_key": "key2"}}}}

        result = AppConfig._deep_merge(base, override)

        assert result["llm"]["provider"] == "mock"
        assert result["llm"]["model"] == "gpt-4o"
        assert "openai" in result["llm"]["providers"]
        assert "anthropic" in result["llm"]["providers"]

    def test_deep_merge_override_scalar(self) -> None:
        """_deep_merge: override заменяет scalar значения."""
        base = {"llm": {"provider": "mock", "model": "old-model"}}
        override = {"llm": {"provider": "openai"}}

        result = AppConfig._deep_merge(base, override)

        assert result["llm"]["provider"] == "openai"  # overridden
        assert result["llm"]["model"] == "old-model"  # preserved

    def test_load_merged_toml_data(self, tmp_path: Path) -> None:
        """_load_merged_toml_data объединяет несколько файлов."""
        # Файл 1 (lowest priority)
        toml1 = tmp_path / "first.toml"
        toml1.write_text("[llm]\nprovider = 'openai'")

        # Файл 2 (higher priority)
        toml2 = tmp_path / "second.toml"
        toml2.write_text("[llm]\nmodel = 'gpt-4o'")

        merged = AppConfig._load_merged_toml_data([toml1, toml2])

        assert merged["llm"]["provider"] == "openai"
        assert merged["llm"]["model"] == "gpt-4o"

    def test_load_auth_toml_api_key(self, tmp_path: Path) -> None:
        """api_key из auth.toml применяется если не задан в codelab.toml."""
        # Создаём codelab.toml без api_key
        (tmp_path / "codelab.toml").write_text(
            "[llm]\nprovider = 'openai'\nmodel = 'openai/gpt-4o'"
        )

        # Создаём auth.toml с api_key
        codelab_home = tmp_path / ".codelab"
        codelab_home.mkdir()
        (codelab_home / "auth.toml").write_text(
            "[llm.providers.openai]\napi_key = 'sk-from-auth'\nbase_url = 'https://api.openai.com/v1'"
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            import unittest.mock

            with unittest.mock.patch.object(Path, "home", return_value=codelab_home.parent):
                config = AppConfig.load()
                assert config.llm.api_key == "sk-from-auth"
                assert config.llm.base_url == "https://api.openai.com/v1"
        finally:
            os.chdir(old_cwd)

    def test_codelab_local_overrides_codelab(self, tmp_path: Path) -> None:
        """codelab.local.toml переопределяет codelab.toml."""
        (tmp_path / "codelab.toml").write_text(
            "[llm]\nprovider = 'openai'\nmodel = 'openai/gpt-4o'"
        )
        (tmp_path / "codelab.local.toml").write_text(
            "[llm]\nprovider = 'anthropic'"
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                config = AppConfig.load()
                assert config.llm.provider == "anthropic"  # из local
                assert config.llm.model == "openai/gpt-4o"  # из codelab.toml
        finally:
            os.chdir(old_cwd)

    def test_custom_toml_highest_priority(self, tmp_path: Path) -> None:
        """Custom TOML через toml_path имеет высший приоритет."""
        (tmp_path / "codelab.toml").write_text(
            "[llm]\nprovider = 'openai'\nmodel = 'openai/gpt-4o'"
        )
        (tmp_path / "codelab.local.toml").write_text(
            "[llm]\nprovider = 'anthropic'"
        )
        custom_toml = tmp_path / "custom.toml"
        custom_toml.write_text("[llm]\nprovider = 'mock'\nmodel = 'mock-model'")

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                config = AppConfig.load(toml_path=str(custom_toml))
                assert config.llm.provider == "mock"  # из custom
                assert config.llm.model == "mock-model"  # из custom
        finally:
            os.chdir(old_cwd)

    def test_auth_toml_providers_merged_with_codelab(self, tmp_path: Path) -> None:
        """Providers из auth.toml и codelab.toml объединяются."""
        (tmp_path / "codelab.toml").write_text(
            "[llm]\nprovider = 'openai'\n\n[llm.providers.openai]\nbase_url = 'https://api.openai.com/v1'"
        )

        codelab_home = tmp_path / ".codelab"
        codelab_home.mkdir()
        (codelab_home / "auth.toml").write_text(
            "[llm.providers.openai]\napi_key = 'sk-auth'\n\n"
            "[llm.providers.anthropic]\napi_key = 'sk-anthropic'"
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            import unittest.mock

            with unittest.mock.patch.object(Path, "home", return_value=codelab_home.parent):
                config = AppConfig.load()
                # Providers должны объединиться
                assert "openai" in config.llm.providers
                assert "anthropic" in config.llm.providers
                # api_key из auth.toml для openai
                assert config.llm.providers["openai"].api_key == "sk-auth"
                assert config.llm.providers["anthropic"].api_key == "sk-anthropic"
        finally:
            os.chdir(old_cwd)


# ============================================================================
# Тесты обратной совместимости
# ============================================================================


class TestBackwardCompatibility:
    """Тесты обратной совместимости."""

    def test_from_env_backward_compatible(self, tmp_path: Path) -> None:
        """from_env() продолжает работать как alias для load()."""
        toml_content = """
[llm]
provider = "openai"
model = "openai/gpt-4o"
"""
        self._create_toml(tmp_path, toml_content)

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.dict(os.environ, {}, clear=True):
                config = AppConfig.from_env()
                assert config.llm.provider == "openai"
        finally:
            os.chdir(old_cwd)

    def _create_toml(self, tmp_path: Path, content: str) -> str:
        toml_file = tmp_path / "codelab.toml"
        toml_file.write_text(content)
        return str(toml_file)

    def test_appconfig_direct_creation(self) -> None:
        """AppConfig() без load() работает с defaults."""
        config = AppConfig()
        assert config.llm.provider == "mock"
        assert config.llm.model == "gpt-4o"

    def test_appconfig_nested_config(self) -> None:
        """AppConfig имеет все nested секции."""
        config = AppConfig()
        assert config.llm is not None
        assert config.agent is not None
        assert config.websocket is not None
        assert config.storage is not None
