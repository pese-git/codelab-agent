"""Тесты покрытия для базовых классов плагинов.

Проверяет lifecycle методы Plugin, HandlerPlugin, EventPlugin и
ConfigurablePlugin, включая их абстрактные базовые реализации.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from codelab.client.infrastructure.plugins.base import (
    ConfigurablePlugin,
    EventPlugin,
    HandlerPlugin,
    Plugin,
    PluginError,
    PluginInitializationError,
    PluginLoadError,
    PluginNotFoundError,
)


class _LifecyclePlugin(Plugin):
    """Конкретный плагин, делегирующий вызовы базовым методам."""

    @property
    def name(self) -> str:
        return super().name  # type: ignore[return-value]

    @property
    def version(self) -> str:
        return super().version  # type: ignore[return-value]

    @property
    def description(self) -> str:
        return super().description  # type: ignore[return-value]

    async def initialize(self, context: Any) -> None:
        await super().initialize(context)

    async def shutdown(self) -> None:
        await super().shutdown()


class _ConcreteHandlerPlugin(HandlerPlugin):
    """Конкретный HandlerPlugin с делегированием get_handlers."""

    @property
    def name(self) -> str:
        return "handler_plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Handler plugin"

    async def initialize(self, context: Any) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    def get_handlers(self) -> dict[str, Any]:
        return super().get_handlers()  # type: ignore[return-value]


class _ConcreteEventPlugin(EventPlugin):
    """Конкретный EventPlugin с делегированием get_event_handlers."""

    @property
    def name(self) -> str:
        return "event_plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Event plugin"

    async def initialize(self, context: Any) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    def get_event_handlers(self) -> dict[type, Any]:
        return super().get_event_handlers()  # type: ignore[return-value]


class _ConcreteConfigurablePlugin(ConfigurablePlugin):
    """Конкретный ConfigurablePlugin с делегированием config-методов."""

    @property
    def name(self) -> str:
        return "configurable_plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Configurable plugin"

    async def initialize(self, context: Any) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    def get_default_config(self) -> dict[str, Any]:
        return super().get_default_config()  # type: ignore[return-value]

    def set_config(self, config: dict[str, Any]) -> None:
        super().set_config(config)


class TestPluginLifecycle:
    """Тесты lifecycle методов базового Plugin."""

    async def test_initialize_runs_base_implementation(self) -> None:
        """Базовый initialize выполняется через super()."""
        plugin = _LifecyclePlugin()

        result = await plugin.initialize(MagicMock())

        assert result is None

    async def test_shutdown_runs_base_implementation(self) -> None:
        """Базовый shutdown выполняется через super()."""
        plugin = _LifecyclePlugin()

        result = await plugin.shutdown()

        assert result is None

    def test_name_property_runs_base_implementation(self) -> None:
        """Базовое свойство name выполняется через super()."""
        plugin = _LifecyclePlugin()

        assert plugin.name is None

    def test_version_property_runs_base_implementation(self) -> None:
        """Базовое свойство version выполняется через super()."""
        plugin = _LifecyclePlugin()

        assert plugin.version is None

    def test_description_property_runs_base_implementation(self) -> None:
        """Базовое свойство description выполняется через super()."""
        plugin = _LifecyclePlugin()

        assert plugin.description is None


class TestHandlerPlugin:
    """Тесты HandlerPlugin."""

    def test_get_handlers_runs_base_implementation(self) -> None:
        """Базовый get_handlers выполняется через super()."""
        plugin = _ConcreteHandlerPlugin()

        assert plugin.get_handlers() is None


class TestEventPlugin:
    """Тесты EventPlugin."""

    def test_get_event_handlers_runs_base_implementation(self) -> None:
        """Базовый get_event_handlers выполняется через super()."""
        plugin = _ConcreteEventPlugin()

        assert plugin.get_event_handlers() is None


class TestConfigurablePlugin:
    """Тесты ConfigurablePlugin."""

    def test_get_default_config_runs_base_implementation(self) -> None:
        """Базовый get_default_config выполняется через super()."""
        plugin = _ConcreteConfigurablePlugin()

        assert plugin.get_default_config() is None

    def test_set_config_runs_base_implementation(self) -> None:
        """Базовый set_config выполняется через super()."""
        plugin = _ConcreteConfigurablePlugin()

        assert plugin.set_config({"debug": True}) is None


class TestPluginErrors:
    """Тесты исключений плагинов."""

    def test_plugin_error_is_exception(self) -> None:
        """PluginError — наследник Exception."""
        assert issubclass(PluginError, Exception)

    def test_plugin_load_error_is_plugin_error(self) -> None:
        """PluginLoadError — наследник PluginError."""
        assert issubclass(PluginLoadError, PluginError)

    def test_plugin_initialization_error_is_plugin_error(self) -> None:
        """PluginInitializationError — наследник PluginError."""
        assert issubclass(PluginInitializationError, PluginError)

    def test_plugin_not_found_error_is_plugin_error(self) -> None:
        """PluginNotFoundError — наследник PluginError."""
        assert issubclass(PluginNotFoundError, PluginError)
