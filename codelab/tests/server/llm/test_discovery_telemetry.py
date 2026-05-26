"""Тесты для discovery и telemetry модулей."""

import pytest

from codelab.server.llm.discovery.static import StaticDiscovery
from codelab.server.llm.models import ModelInfo
from codelab.server.llm.telemetry.noop import NoOpTelemetry


class TestStaticDiscovery:
    """Тесты для StaticDiscovery."""

    @pytest.mark.asyncio
    async def test_discover_models_with_list(self) -> None:
        """Проверить discovery со списком моделей."""
        models = [
            ModelInfo(id="gpt-4o", provider_id="openai"),
            ModelInfo(id="o3", provider_id="openai"),
        ]
        discovery = StaticDiscovery(models)
        result = await discovery.discover_models()
        assert len(result) == 2
        assert result[0].id == "gpt-4o"

    @pytest.mark.asyncio
    async def test_discover_models_empty(self) -> None:
        """Проверить discovery с пустым списком."""
        discovery = StaticDiscovery()
        result = await discovery.discover_models()
        assert result == []

    @pytest.mark.asyncio
    async def test_discover_models_none(self) -> None:
        """Проверить discovery с None."""
        discovery = StaticDiscovery(models=None)
        result = await discovery.discover_models()
        assert result == []


class TestNoOpTelemetry:
    """Тесты для NoOpTelemetry."""

    @pytest.mark.asyncio
    async def test_record_request(self) -> None:
        """Проверить record_request — silent pass-through."""
        telemetry = NoOpTelemetry()
        # Не должно вызывать ошибок
        await telemetry.record_request("openai", "gpt-4o", 100.0, True)
        await telemetry.record_request("openai", "gpt-4o", 200.0, False)

    @pytest.mark.asyncio
    async def test_record_cost(self) -> None:
        """Проверить record_cost — silent pass-through."""
        telemetry = NoOpTelemetry()
        # Не должно вызывать ошибок
        await telemetry.record_cost("openai", "gpt-4o", 0.001)
