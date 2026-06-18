"""Тесты для непокрытых веток серверного DI-контейнера.

Покрывают ObservabilityFlushManager, провайдеры observability,
провайдер периодического flush и fallback на MockLLMProvider.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.config import AppConfig
from codelab.server.di import (
    LLMProvider_,
    ObservabilityFlushManager,
    ObservabilityFlushProvider,
    ObservabilityProvider,
)
from codelab.server.llm.base import LLMConfig
from codelab.server.llm.errors import ProviderNotFoundError

_LOGGER_PATH = "codelab.server.di.logger"


class TestObservabilityFlushManager:
    """Тесты менеджера периодического flush observability данных."""

    @pytest.mark.asyncio
    async def test_start_disabled_logs_and_returns(self) -> None:
        """При enabled=False менеджер логирует отключение и не запускает цикл."""
        manager = ObservabilityFlushManager(enabled=False)

        with patch(_LOGGER_PATH) as mock_logger:
            await manager.start(
                tracer=MagicMock(),
                timeline=MagicMock(),
                metrics=MagicMock(),
                span_exporter=MagicMock(),
                event_exporter=MagicMock(),
                metrics_exporter=MagicMock(),
            )

        assert manager._task is None
        mock_logger.info.assert_called_once()
        assert "disabled" in str(mock_logger.info.call_args).lower()

    @pytest.mark.asyncio
    async def test_flush_loop_exception_logged(self) -> None:
        """Исключение в цикле flush логируется и не прерывает цикл."""
        manager = ObservabilityFlushManager(enabled=True, flush_interval=60)
        manager.flush_all = AsyncMock()

        with patch(_LOGGER_PATH) as mock_logger:
            with patch.object(
                asyncio,
                "sleep",
                side_effect=[None, RuntimeError("boom"), asyncio.CancelledError()],
            ):
                await manager._flush_loop()

        mock_logger.error.assert_called_once()
        assert "Error in observability flush loop" in str(mock_logger.error.call_args)

    @pytest.mark.asyncio
    async def test_flush_all_exception_logged(self) -> None:
        """Исключение при flush_all логируется и не пробрасывается наружу."""
        manager = ObservabilityFlushManager(enabled=True)
        manager._span_exporter = MagicMock()
        manager._span_exporter.flush = MagicMock(side_effect=RuntimeError("flush failed"))
        manager._event_exporter = MagicMock()
        manager._metrics_exporter = MagicMock()
        manager._metrics = MagicMock()

        with patch(_LOGGER_PATH) as mock_logger:
            await manager.flush_all()

        mock_logger.error.assert_called_once()
        assert "Failed to flush observability data" in str(mock_logger.error.call_args)


class TestObservabilityProvider:
    """Тесты провайдеров observability компонентов."""

    def test_get_file_span_exporter(self) -> None:
        """get_file_span_exporter создаёт экспортёр с параметрами конфига."""
        provider = ObservabilityProvider()
        config = AppConfig()
        config.observability.export_dir = "/tmp/obs"
        config.observability.max_file_size = 1024

        exporter = provider.get_file_span_exporter(config)

        assert exporter.export_dir.name == "spans"
        assert exporter.max_file_size == 1024

    def test_get_file_event_exporter(self) -> None:
        """get_file_event_exporter создаёт экспортёр событий."""
        provider = ObservabilityProvider()
        config = AppConfig()
        config.observability.export_dir = "/tmp/obs"

        exporter = provider.get_file_event_exporter(config)

        assert exporter.export_dir.name == "events"

    def test_get_file_metrics_exporter(self) -> None:
        """get_file_metrics_exporter создаёт экспортёр метрик."""
        provider = ObservabilityProvider()
        config = AppConfig()
        config.observability.export_dir = "/tmp/obs"

        exporter = provider.get_file_metrics_exporter(config)

        assert exporter.export_dir.name == "metrics"


class TestObservabilityFlushProvider:
    """Тесты провайдера менеджера периодического flush."""

    @pytest.fixture
    def _flush_deps(self) -> dict[str, MagicMock]:
        """Зависимости для get_flush_manager."""
        return {
            "tracer": MagicMock(),
            "timeline": MagicMock(),
            "metrics": MagicMock(),
            "span_exporter": MagicMock(),
            "event_exporter": MagicMock(),
            "metrics_exporter": MagicMock(),
        }

    @pytest.mark.asyncio
    async def test_get_flush_manager_enabled_lifecycle(
        self,
        _flush_deps: dict[str, MagicMock],
    ) -> None:
        """Провайдер запускает менеджер, возвращает его и выполняет cleanup."""
        provider = ObservabilityFlushProvider()
        config = AppConfig()
        config.observability.enabled = True
        config.observability.flush_interval = 60

        gen = provider.get_flush_manager(config=config, **_flush_deps)
        manager = await gen.__anext__()

        assert isinstance(manager, ObservabilityFlushManager)
        assert manager._task is not None

        # Подменяем stop, чтобы cleanup дошёл до await manager.stop()
        # независимо от поведения фоновой задачи.
        manager.stop = AsyncMock()

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

        manager.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_flush_manager_disabled(
        self,
        _flush_deps: dict[str, MagicMock],
    ) -> None:
        """Провайдер корректно работает когда flush выключен в конфиге."""
        provider = ObservabilityFlushProvider()
        config = AppConfig()
        config.observability.enabled = False

        gen = provider.get_flush_manager(config=config, **_flush_deps)
        manager = await gen.__anext__()

        assert isinstance(manager, ObservabilityFlushManager)
        assert manager._task is None

        await gen.aclose()


class TestLLMProviderFallback:
    """Тесты fallback на MockLLMProvider."""

    @pytest.mark.asyncio
    async def test_get_llm_provider_fallback_to_mock(
        self,
    ) -> None:
        """При ProviderNotFoundError создаётся и инициализируется MockLLMProvider."""
        provider = LLMProvider_()
        config = AppConfig()
        config.llm.provider = "unknown_provider"
        config.llm.model = "gpt-test"
        config.llm.temperature = 0.5
        config.llm.max_tokens = 1024
        config.llm.timeout.connect = 1.0
        config.llm.timeout.read = 2.0
        config.llm.timeout.write = 3.0
        config.llm.timeout.pool = 4.0

        registry = MagicMock()
        registry.get_provider = AsyncMock(side_effect=ProviderNotFoundError("not found"))

        mock_instance = AsyncMock()
        mock_instance.initialize = AsyncMock()

        with patch("codelab.server.di.MockLLMProvider", return_value=mock_instance):
            result = await provider.get_llm_provider(config, registry)

        assert result is mock_instance
        registry.get_provider.assert_awaited_once_with("unknown_provider")
        mock_instance.initialize.assert_awaited_once()

        call_args = mock_instance.initialize.call_args
        passed_config = call_args[0][0]
        assert isinstance(passed_config, LLMConfig)
        assert passed_config.model == "gpt-test"
        assert passed_config.temperature == 0.5
