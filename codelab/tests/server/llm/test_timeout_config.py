"""Тесты для LLMTimeoutConfig и интеграции таймаутов."""

from codelab.server.llm.base import LLMConfig, LLMTimeoutConfig


class TestLLMTimeoutConfig:
    """Тесты для LLMTimeoutConfig."""

    def test_default_values(self) -> None:
        """Проверить значения по умолчанию."""
        timeout = LLMTimeoutConfig()
        assert timeout.connect == 30.0
        assert timeout.read == 300.0
        assert timeout.write == 30.0
        assert timeout.pool == 30.0

    def test_custom_values(self) -> None:
        """Проверить кастомные значения."""
        timeout = LLMTimeoutConfig(connect=10.0, read=120.0, write=5.0, pool=15.0)
        assert timeout.connect == 10.0
        assert timeout.read == 120.0
        assert timeout.write == 5.0
        assert timeout.pool == 15.0

    def test_partial_override(self) -> None:
        """Проверить частичное переопределение."""
        timeout = LLMTimeoutConfig(read=60.0)
        assert timeout.connect == 30.0  # default
        assert timeout.read == 60.0  # overridden
        assert timeout.write == 30.0  # default
        assert timeout.pool == 30.0  # default


class TestLLMConfigWithTimeout:
    """Тесты для LLMConfig с timeout."""

    def test_default_timeout(self) -> None:
        """Проверить что LLMConfig имеет default timeout."""
        config = LLMConfig()
        assert isinstance(config.timeout, LLMTimeoutConfig)
        assert config.timeout.read == 300.0

    def test_custom_timeout(self) -> None:
        """Проверить кастомный timeout в LLMConfig."""
        timeout = LLMTimeoutConfig(connect=5.0, read=60.0)
        config = LLMConfig(timeout=timeout)
        assert config.timeout.connect == 5.0
        assert config.timeout.read == 60.0

    def test_timeout_preserved_with_other_fields(self) -> None:
        """Проверить что timeout сохраняется вместе с другими полями."""
        config = LLMConfig(
            api_key="test-key",
            model="gpt-4",
            temperature=0.5,
            timeout=LLMTimeoutConfig(read=120.0),
        )
        assert config.api_key == "test-key"
        assert config.model == "gpt-4"
        assert config.temperature == 0.5
        assert config.timeout.read == 120.0
