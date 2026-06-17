"""Дополнительные тесты для покрытия PluginManager.

Покрывает:
- load_plugin: spec is None, generic exception
- initialize_all: сбор ошибок
- shutdown_plugin: exception propagation
- shutdown_all: error logging
- list_initialized_plugins
- unregister_plugin
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from dishka import Provider, Scope, make_container

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.infrastructure.handler_registry import HandlerRegistry
from codelab.client.infrastructure.plugins.base import (
    Plugin,
    PluginInitializationError,
    PluginLoadError,
)
from codelab.client.infrastructure.plugins.context import PluginContext
from codelab.client.infrastructure.plugins.manager import PluginManager


def _make_test_container() -> Any:
    """Создаёт минимальный dishka контейнер для тестов."""

    class TestProvider(Provider):
        scope = Scope.APP

    return make_container(TestProvider())


def _make_context() -> PluginContext:
    """Создаёт тестовый PluginContext."""
    return PluginContext(
        container=_make_test_container(),
        event_bus=EventBus(),
        handler_registry=HandlerRegistry(),
        logger=None,
    )


class SimpleTestPlugin(Plugin):
    """Простой тестовый плагин."""

    def __init__(self) -> None:
        self.initialized = False
        self.shutdown_called = False

    @property
    def name(self) -> str:
        return "simple_test_plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Simple test plugin"

    async def initialize(self, context: PluginContext) -> None:
        self.initialized = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


class TestPluginManagerLoadPluginCoverage:
    """Тесты для покрытия load_plugin."""

    def test_load_plugin_raises_when_spec_is_none(self) -> None:
        """load_plugin бросает PluginLoadError если spec None."""
        manager = PluginManager(_make_context())

        with TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "plugin.py"
            plugin_file.write_text("# empty")

            with patch(
                "importlib.util.spec_from_file_location",
                return_value=None,
            ):
                with pytest.raises(PluginLoadError, match="Could not load spec"):
                    manager.load_plugin(plugin_file)

    def test_load_plugin_raises_on_generic_exception(self) -> None:
        """load_plugin оборачивает непредвиденные исключения."""
        manager = PluginManager(_make_context())

        with TemporaryDirectory() as tmpdir:
            plugin_file = Path(tmpdir) / "plugin.py"
            plugin_file.write_text("# empty")

            with patch(
                "importlib.util.spec_from_file_location",
                side_effect=RuntimeError("boom"),
            ):
                with pytest.raises(PluginLoadError, match="Failed to load plugin"):
                    manager.load_plugin(plugin_file)


class TestPluginManagerInitializeAllCoverage:
    """Тесты для покрытия initialize_all."""

    @pytest.mark.asyncio
    async def test_initialize_all_collects_errors(self) -> None:
        """initialize_all собирает ошибки и бросает PluginInitializationError."""
        manager = PluginManager(_make_context())
        plugin = SimpleTestPlugin()

        # Заставляем initialize бросать ошибку
        plugin.initialize = AsyncMock(side_effect=RuntimeError("init failed"))  # type: ignore[method-assign]

        manager.register_plugin(plugin)

        with pytest.raises(PluginInitializationError) as exc_info:
            await manager.initialize_all()

        assert "simple_test_plugin" in str(exc_info.value)
        assert "init failed" in str(exc_info.value)


class TestPluginManagerShutdownCoverage:
    """Тесты для покрытия shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_plugin_propagates_exception(self) -> None:
        """shutdown_plugin пробрасывает исключение из shutdown плагина."""
        manager = PluginManager(_make_context())
        plugin = SimpleTestPlugin()
        plugin.shutdown = AsyncMock(side_effect=RuntimeError("shutdown failed"))  # type: ignore[method-assign]

        manager.register_plugin(plugin)
        await manager.initialize_plugin(plugin.name)

        with pytest.raises(RuntimeError, match="shutdown failed"):
            await manager.shutdown_plugin(plugin.name)

    @pytest.mark.asyncio
    async def test_shutdown_all_logs_error(self) -> None:
        """shutdown_all логирует ошибки и не прерывается."""
        manager = PluginManager(_make_context())
        plugin = SimpleTestPlugin()
        plugin.shutdown = AsyncMock(side_effect=RuntimeError("shutdown failed"))  # type: ignore[method-assign]

        manager.register_plugin(plugin)
        await manager.initialize_plugin(plugin.name)

        # Не должно бросать исключение
        await manager.shutdown_all()

        assert plugin.name not in manager.list_initialized_plugins()


class TestPluginManagerListAndUnregisterCoverage:
    """Тесты для покрытия list_initialized_plugins и unregister_plugin."""

    @pytest.mark.asyncio
    async def test_list_initialized_plugins_returns_initialized(self) -> None:
        """list_initialized_plugins возвращает инициализированные плагины."""
        manager = PluginManager(_make_context())
        plugin = SimpleTestPlugin()

        manager.register_plugin(plugin)
        assert manager.list_initialized_plugins() == []

        await manager.initialize_plugin(plugin.name)
        assert manager.list_initialized_plugins() == [plugin.name]

    def test_unregister_plugin_removes_uninitialized(self) -> None:
        """unregister_plugin удаляет неинициализированный плагин."""
        manager = PluginManager(_make_context())
        plugin = SimpleTestPlugin()

        manager.register_plugin(plugin)
        manager.unregister_plugin(plugin.name)

        assert manager.get_plugin(plugin.name) is None

    @pytest.mark.asyncio
    async def test_unregister_initialized_raises_error(self) -> None:
        """unregister_plugin бросает ValueError для инициализированного плагина."""
        manager = PluginManager(_make_context())
        plugin = SimpleTestPlugin()

        manager.register_plugin(plugin)
        await manager.initialize_plugin(plugin.name)

        with pytest.raises(ValueError, match="still initialized"):
            manager.unregister_plugin(plugin.name)
