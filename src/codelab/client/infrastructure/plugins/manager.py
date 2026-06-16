"""Plugin Manager - управление загрузкой и выполнением плагинов.

PluginManager отвечает за:
- Загрузку плагинов из файлов
- Инициализацию и завершение работы плагинов
- Управление жизненным циклом плагинов
- Регистрацию handlers из плагинов
- Подписку на события из плагинов
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from codelab.client.infrastructure.plugins.base import (
    EventPlugin,
    HandlerPlugin,
    Plugin,
    PluginInitializationError,
    PluginLoadError,
    PluginNotFoundError,
)
from codelab.client.infrastructure.plugins.context import PluginContext

if TYPE_CHECKING:
    pass


class PluginManager:
    """Управляет загрузкой, инициализацией и жизненным циклом плагинов.

    PluginManager обеспечивает единую точку управления плагинами:
    - Загружает плагины из файлов
    - Инициализирует их с PluginContext
    - Регистрирует handlers через HandlerRegistry
    - Подписывает на события через EventBus
    - Завершает работу при выключении

    Пример использования:
        manager = PluginManager(context)

        # Загрузить плагин
        plugin = manager.load_plugin(Path("plugins/my_plugin.py"))

        # Инициализировать все плагины
        await manager.initialize_all()

        # Получить информацию о плагинах
        plugins = manager.list_plugins()

        # Выключить все плагины
        await manager.shutdown_all()
    """

    def __init__(self, context: PluginContext) -> None:
        """Инициализировать PluginManager.

        Args:
            context: PluginContext с доступом к DI, EventBus и HandlerRegistry
        """
        self._context = context
        self._plugins: dict[str, Plugin] = {}
        self._loaded_plugins: list[str] = []
        self._logger = structlog.get_logger()

    def load_plugin(self, plugin_path: Path) -> Plugin:
        """Динамически загрузить плагин из файла.

        Загружает Python модуль из файла и ищет класс, наследующий Plugin.
        Если найдено несколько классов или ни одного, вызывает ошибку.

        Args:
            plugin_path: Путь к файлу плагина (например, "plugins/my_plugin.py")

        Returns:
            Загруженный плагин (ещё не инициализирован)

        Raises:
            PluginLoadError: Если плагин не может быть загружен или не содержит Plugin класс
            FileNotFoundError: Если файл плагина не найден
        """
        if not plugin_path.exists():
            raise FileNotFoundError(f"Plugin file not found: {plugin_path}")

        try:
            # Создать модуль из файла
            spec = importlib.util.spec_from_file_location(
                f"plugin_{plugin_path.stem}",
                plugin_path,
            )

            if spec is None or spec.loader is None:
                raise PluginLoadError(
                    f"Could not load spec from {plugin_path}"
                )

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Найти класс, наследующий Plugin
            plugin_class = None
            for item_name in dir(module):
                item = getattr(module, item_name)
                if (
                    isinstance(item, type)
                    and issubclass(item, Plugin)
                    and item is not Plugin
                    and item is not HandlerPlugin
                    and item is not EventPlugin
                ):
                    if plugin_class is not None:
                        raise PluginLoadError(
                            f"Multiple Plugin classes found in {plugin_path}"
                        )
                    plugin_class = item

            if plugin_class is None:
                raise PluginLoadError(
                    f"No Plugin class found in {plugin_path}"
                )

            # Создать экземпляр плагина
            plugin = plugin_class()

            self._logger.info(
                "plugin_loaded",
                plugin_name=plugin.name,
                plugin_version=plugin.version,
                plugin_path=str(plugin_path),
            )

            return plugin
        except PluginLoadError:
            raise
        except Exception as e:
            raise PluginLoadError(
                f"Failed to load plugin from {plugin_path}: {e}"
            ) from e

    def register_plugin(self, plugin: Plugin) -> None:
        """Зарегистрировать загруженный плагин.

        Добавляет плагин в управление PluginManager, но не инициализирует его.

        Args:
            plugin: Экземпляр плагина для регистрации

        Raises:
            ValueError: Если плагин с таким именем уже зарегистрирован
        """
        if plugin.name in self._plugins:
            raise ValueError(
                f"Plugin with name '{plugin.name}' already registered"
            )

        self._plugins[plugin.name] = plugin
        self._logger.debug(
            "plugin_registered",
            plugin_name=plugin.name,
        )

    async def initialize_plugin(self, plugin_name: str) -> None:
        """Инициализировать конкретный плагин.

        Args:
            plugin_name: Имя плагина для инициализации

        Raises:
            PluginNotFoundError: Если плагин не найден
            PluginInitializationError: Если инициализация не удалась
        """
        if plugin_name not in self._plugins:
            raise PluginNotFoundError(
                f"Plugin '{plugin_name}' not found"
            )

        plugin = self._plugins[plugin_name]

        try:
            await plugin.initialize(self._context)

            # Если это HandlerPlugin, зарегистрировать handlers
            if isinstance(plugin, HandlerPlugin):
                handlers = plugin.get_handlers()
                for handler_name, handler in handlers.items():
                    self._context.handler_registry.register(
                        handler_name,
                        handler,
                    )
                    self._logger.debug(
                        "handler_registered_from_plugin",
                        plugin_name=plugin.name,
                        handler_name=handler_name,
                    )

            # Если это EventPlugin, подписаться на события
            if isinstance(plugin, EventPlugin):
                event_handlers = plugin.get_event_handlers()
                for event_type, handler in event_handlers.items():
                    self._context.event_bus.subscribe(
                        event_type,
                        handler,
                    )
                    self._logger.debug(
                        "event_handler_registered_from_plugin",
                        plugin_name=plugin.name,
                        event_type=event_type.__name__,
                    )

            self._loaded_plugins.append(plugin_name)

            self._logger.info(
                "plugin_initialized",
                plugin_name=plugin.name,
            )
        except Exception as e:
            self._logger.error(
                "plugin_initialization_failed",
                plugin_name=plugin_name,
                error=str(e),
                exc_info=True,
            )
            raise PluginInitializationError(
                f"Failed to initialize plugin '{plugin_name}': {e}"
            ) from e

    async def initialize_all(self) -> None:
        """Инициализировать все загруженные плагины.

        Плагины инициализируются в том порядке, в котором они были загружены.

        Raises:
            PluginInitializationError: Если хотя бы один плагин не инициализирован
        """
        errors = []

        for plugin_name in self._plugins:
            if plugin_name not in self._loaded_plugins:
                try:
                    await self.initialize_plugin(plugin_name)
                except PluginInitializationError as e:
                    errors.append((plugin_name, e))

        if errors:
            error_msgs = "\n".join(
                f"  {name}: {str(error)}" for name, error in errors
            )
            raise PluginInitializationError(
                f"Failed to initialize {len(errors)} plugin(s):\n{error_msgs}"
            )

    async def shutdown_plugin(self, plugin_name: str) -> None:
        """Завершить работу конкретного плагина.

        Args:
            plugin_name: Имя плагина для завершения

        Raises:
            PluginNotFoundError: Если плагин не найден
        """
        if plugin_name not in self._plugins:
            raise PluginNotFoundError(
                f"Plugin '{plugin_name}' not found"
            )

        plugin = self._plugins[plugin_name]

        try:
            await plugin.shutdown()
            if plugin_name in self._loaded_plugins:
                self._loaded_plugins.remove(plugin_name)

            self._logger.info(
                "plugin_shutdown",
                plugin_name=plugin.name,
            )
        except Exception as e:
            self._logger.error(
                "plugin_shutdown_failed",
                plugin_name=plugin_name,
                error=str(e),
                exc_info=True,
            )
            raise

    async def shutdown_all(self) -> None:
        """Завершить работу всех инициализированных плагинов.

        Плагины выключаются в обратном порядке инициализации.
        Ошибки логируются, но не прерывают выключение других плагинов.
        """
        # Выключать в обратном порядке инициализации
        for plugin_name in reversed(self._loaded_plugins):
            try:
                await self.shutdown_plugin(plugin_name)
            except Exception as e:
                self._logger.error(
                    "plugin_shutdown_error",
                    plugin_name=plugin_name,
                    error=str(e),
                    exc_info=True,
                )

    def get_plugin(self, plugin_name: str) -> Plugin | None:
        """Получить плагин по имени.

        Args:
            plugin_name: Имя плагина

        Returns:
            Плагин или None если не найден
        """
        return self._plugins.get(plugin_name)

    def list_plugins(self) -> list[tuple[str, str, str]]:
        """Получить список (name, version, description) всех плагинов.

        Returns:
            Список кортежей (name, version, description)
        """
        return [
            (p.name, p.version, p.description)
            for p in self._plugins.values()
        ]

    def list_initialized_plugins(self) -> list[str]:
        """Получить список имён инициализированных плагинов.

        Returns:
            Список имён плагинов в порядке инициализации
        """
        return self._loaded_plugins.copy()

    def is_plugin_initialized(self, plugin_name: str) -> bool:
        """Проверить, инициализирован ли плагин.

        Args:
            plugin_name: Имя плагина

        Returns:
            True если плагин инициализирован, иначе False
        """
        return plugin_name in self._loaded_plugins

    def unregister_plugin(self, plugin_name: str) -> None:
        """Удалить плагин из управления (без shutdown).

        Args:
            plugin_name: Имя плагина

        Raises:
            ValueError: Если попытаться удалить инициализированный плагин
        """
        if plugin_name in self._loaded_plugins:
            raise ValueError(
                f"Cannot unregister plugin '{plugin_name}': "
                "it is still initialized. Call shutdown_plugin first."
            )

        if plugin_name in self._plugins:
            del self._plugins[plugin_name]
            self._logger.debug(
                "plugin_unregistered",
                plugin_name=plugin_name,
            )
