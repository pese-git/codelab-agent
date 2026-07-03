"""MCPSessionManager — управление MCP серверами для сессий.

Инкапсулирует всю логику работы с MCP:
- Инициализация MCP серверов при создании/загрузке сессии
- Defensive re-initialization при reconnect
- Управление MCP prompts как slash-командами
- Отправка available_commands_update при изменениях
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from ..mcp import MCPManager, MCPManagerError
from ..mcp.models import MCPServerConfig
from ..mcp.prompt_mapper import mcp_prompts_to_available_commands
from ..messages import ACPMessage

if TYPE_CHECKING:
    from ..protocol.session_runtime import SessionRuntimeRegistry
    from ..protocol.state import SessionState
    from ..tools.base import ToolRegistry

logger = structlog.get_logger()


def _get_command_name(cmd: Any) -> str:
    """Извлекает имя команды из dict или AvailableCommand."""
    if isinstance(cmd, dict):
        return cmd.get("name", "")
    return getattr(cmd, "name", "")


class MCPSessionManager:
    """Управляет MCP серверами для сессий.

    Отвечает за:
    - Инициализацию MCP серверов при session/new и session/load
    - Defensive re-initialization при WebSocket reconnect
    - Регистрацию MCP prompts как slash-команд
    - Отправку available_commands_update при изменениях

    Notifications публикуются в SessionNotificationBus, транспорт подписывается
    на bus и доставляет сообщения клиенту.

    Attributes:
        runtime_registry: Реестр runtime-состояний сессий.
        tool_registry: Глобальный реестр инструментов (для native tools).
    """

    def __init__(
        self,
        runtime_registry: SessionRuntimeRegistry,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """Инициализирует MCPSessionManager.

        Args:
            runtime_registry: Реестр runtime-состояний сессий.
            tool_registry: Глобальный реестр инструментов (опционально).
        """
        self._runtime_registry = runtime_registry
        self._tool_registry = tool_registry

    async def setup_if_needed(
        self,
        session_state: SessionState,
        params: dict[str, Any],
    ) -> None:
        """Инициализирует MCP серверы если нужно.

        Вызывается из session/new и session/load.
        Не дублирует инициализацию если MCP уже есть в runtime registry.

        Args:
            session_state: Состояние сессии.
            params: Параметры из запроса (содержат mcpServers).
        """
        mcp_servers = params.get("mcpServers", [])
        if not mcp_servers or not isinstance(mcp_servers, list):
            return

        # Проверить есть ли уже MCP в registry
        runtime = await self._runtime_registry.get(session_state.session_id)
        if runtime and runtime.mcp_manager is not None:
            return  # Уже инициализирован

        await self._initialize_mcp_servers(session_state, mcp_servers)

    async def ensure_initialized(
        self,
        session: SessionState,
    ) -> MCPManager | None:
        """Убеждается что MCP серверы инициализированы для сессии.

        Defensive check: если сессия имеет mcp_servers в state, но mcp_manager
        отсутствует в runtime registry (например, после WebSocket reconnect),
        автоматически переинициализирует MCP серверы.

        Также восстанавливает mcp_prompt_handlers если они потеряны.

        Согласно ACP протоколу, клиент ДОЛЖЕН вызывать session/load после
        reconnect для восстановления MCP соединений. Этот метод обеспечивает
        graceful degradation если клиент нарушает протокол.

        Args:
            session: Состояние сессии с mcp_servers.

        Returns:
            MCPManager если инициализирован, иначе None.
        """
        runtime = await self._runtime_registry.get(session.session_id)
        if runtime and runtime.mcp_manager is not None:
            # Восстанавливаем handlers если они потеряны
            if not runtime.mcp_prompt_handlers and session.mcp_servers:
                await self._restore_mcp_prompts(session, runtime.mcp_manager)
            return runtime.mcp_manager

        # MCP manager отсутствует, но есть конфигурация — переинициализировать
        if session.mcp_servers:
            logger.warning(
                "mcp_servers_configured_but_not_initialized",
                session_id=session.session_id,
                mcp_server_count=len(session.mcp_servers),
                hint="Client should call session/load after WebSocket reconnect",
            )
            await self._initialize_mcp_servers(session, session.mcp_servers)

            # Получить обновлённый mcp_manager
            runtime = await self._runtime_registry.get(session.session_id)
            if runtime:
                return runtime.mcp_manager

        return None

    async def _restore_mcp_prompts(
        self,
        session: SessionState,
        mcp_manager: MCPManager,
    ) -> None:
        """Восстанавливает mcp_prompt_handlers в runtime registry.

        Вызывается когда mcp_manager уже есть в runtime registry,
        но runtime.mcp_prompt_handlers пуст (handlers не сохраняются
        между restart сервера).

        Args:
            session: Состояние сессии для получения mcp_servers.
            mcp_manager: Существующий MCPManager из runtime registry.
        """
        runtime = await self._runtime_registry.get(session.session_id)
        if runtime is None:
            logger.warning(
                "cannot_restore_mcp_prompts: runtime not found",
                session_id=session.session_id,
            )
            return

        # Очищаем старые MCP prompts из available_commands (оставляем built-in)
        builtin_names = {"status", "mode", "help"}
        session.available_commands = [
            cmd for cmd in session.available_commands
            if _get_command_name(cmd) in builtin_names
        ]
        runtime.mcp_prompt_handlers.clear()
        session.mcp_prompt_handlers.clear()

        # Получаем prompts от всех серверов ОДИН раз
        try:
            all_prompts = await mcp_manager.get_all_prompts()
        except Exception as e:
            logger.warning(
                "failed to get prompts during restore",
                session_id=session.session_id,
                error=str(e),
            )
            return

        # Регистрируем prompts для каждого сервера
        for server_config in session.mcp_servers:
            if not isinstance(server_config, dict):
                continue
            server_name = server_config.get("name")
            if not server_name:
                continue

            server_prompts = all_prompts.get(server_name, [])
            if not server_prompts:
                continue

            self._register_mcp_prompts_from_list(
                session, mcp_manager, server_name, server_prompts
            )

        # Копируем handlers из session в runtime (основное хранилище)
        runtime.mcp_prompt_handlers.update(session.mcp_prompt_handlers)
        session.mcp_prompt_handlers.clear()

        logger.info(
            "restored_mcp_prompt_handlers",
            session_id=session.session_id,
            handlers_count=len(runtime.mcp_prompt_handlers),
        )

    async def send_available_commands_update(
        self,
        session_state: SessionState,
        mcp_manager: MCPManager,
    ) -> None:
        """Формирует и отправляет available_commands_update клиенту.

        Объединяет native tools, MCP tools и slash commands из session_state
        в единый список и отправляет notification клиенту.

        Args:
            session_state: Состояние сессии для получения slash commands.
            mcp_manager: MCP менеджер для получения tools.
        """
        try:
            # Собираем все инструменты
            mcp_tools = mcp_manager.get_all_tools()
            native_tools = (
                self._tool_registry.get_available_tools("")
                if self._tool_registry
                else []
            )
            all_tools = native_tools + mcp_tools

            # Формируем availableCommands
            available_commands: list[dict[str, Any]] = [
                {"name": tool.name, "description": tool.description or ""}
                for tool in all_tools
            ]

            # Добавляем slash-команды из session_state
            for cmd in session_state.available_commands:
                if isinstance(cmd, dict):
                    available_commands.append(cmd)
                elif hasattr(cmd, "model_dump"):
                    available_commands.append(cmd.model_dump(exclude_none=True))
                else:
                    available_commands.append(cmd)

            # Отправляем notification
            notification = ACPMessage.notification(
                "session/update",
                {
                    "sessionId": session_state.session_id,
                    "update": {
                        "sessionUpdate": "available_commands_update",
                        "availableCommands": available_commands,
                    },
                },
            )
            await self._send_message(notification, session_state.session_id)

            logger.info(
                "sent_available_commands_update",
                session_id=session_state.session_id,
                tools_count=len(all_tools),
                slash_commands_count=len(session_state.available_commands),
            )
        except Exception as e:
            logger.error(
                "failed_to_send_available_commands_update",
                session_id=session_state.session_id,
                error=str(e),
            )

    async def _initialize_mcp_servers(
        self,
        session_state: SessionState,
        mcp_servers: list[dict[str, Any]],
    ) -> None:
        """Инициализирует MCP серверы для сессии.

        Создаёт MCPManager, подключается к каждому MCP серверу,
        получает инструменты и промпты, регистрирует их для сессии.

        Args:
            session_state: Состояние сессии для сохранения MCPManager.
            mcp_servers: Список конфигураций MCP серверов из параметров session/new.
        """
        if not mcp_servers:
            return

        # Создаём MCPManager для этой сессии
        mcp_manager = MCPManager(session_state.session_id)
        await self._runtime_registry.set_mcp_manager(
            session_state.session_id, mcp_manager
        )

        # Регистрируем callback для отправки available_commands_update при изменении инструментов
        async def _on_mcp_tools_changed() -> None:
            await self.send_available_commands_update(session_state, mcp_manager)

        mcp_manager.register_tool_change_callback(_on_mcp_tools_changed)

        # Регистрируем callback для уведомлений о статусе серверов
        async def _on_mcp_server_status_changed() -> None:
            try:
                servers_info = mcp_manager.get_servers_info()
                for server_info in servers_info:
                    status_text = (
                        f"MCP server '{server_info['name']}' "
                        f"status: {server_info['state']}"
                    )
                    notification = ACPMessage.notification(
                        "session/update",
                        {
                            "sessionId": session_state.session_id,
                            "update": {
                                "sessionUpdate": "agent_message_chunk",
                                "content": {
                                    "type": "text",
                                    "text": f"[system] {status_text}",
                                },
                            },
                        },
                    )
                    await self._send_message(notification, session_state.session_id)
            except Exception as e:
                logger.error(
                    "failed_to_send_mcp_server_status_notification",
                    session_id=session_state.session_id,
                    error=str(e),
                )

        mcp_manager.register_server_status_callback(_on_mcp_server_status_changed)

        # Регистрируем callback для отправки available_commands_update при изменении prompts
        async def _on_mcp_prompts_changed() -> None:
            try:
                runtime = await self._runtime_registry.get(session_state.session_id)
                if runtime is None:
                    logger.warning(
                        "cannot_handle_prompts_change: runtime not found",
                        session_id=session_state.session_id,
                    )
                    return

                # Очищаем старые MCP prompts (оставляем built-in)
                builtin_names = {"status", "mode", "help"}
                session_state.available_commands = [
                    cmd for cmd in session_state.available_commands
                    if _get_command_name(cmd) in builtin_names
                ]
                runtime.mcp_prompt_handlers.clear()
                session_state.mcp_prompt_handlers.clear()

                # Получаем prompts от всех серверов и регистрируем заново
                all_prompts = await mcp_manager.get_all_prompts()
                for server_config in session_state.mcp_servers:
                    if not isinstance(server_config, dict):
                        continue
                    server_name = server_config.get("name")
                    if not server_name:
                        continue
                    server_prompts = all_prompts.get(server_name, [])
                    if server_prompts:
                        self._register_mcp_prompts_from_list(
                            session_state, mcp_manager, server_name, server_prompts
                        )

                # Копируем handlers из session в runtime (основное хранилище)
                runtime.mcp_prompt_handlers.update(session_state.mcp_prompt_handlers)
                session_state.mcp_prompt_handlers.clear()

                # Отправляем notification с обновлённым списком команд
                await self.send_available_commands_update(session_state, mcp_manager)

                logger.info(
                    "refreshed_mcp_prompts",
                    session_id=session_state.session_id,
                    prompts_count=len(runtime.mcp_prompt_handlers),
                )
            except Exception as e:
                logger.error(
                    "failed_to_handle_mcp_prompts_change",
                    session_id=session_state.session_id,
                    error=str(e),
                )

        mcp_manager.register_prompt_change_callback(_on_mcp_prompts_changed)

        for server_config_dict in mcp_servers:
            # Пропускаем невалидные конфигурации
            if not isinstance(server_config_dict, dict):
                logger.warning(
                    "invalid_mcp_server_config",
                    session_id=session_state.session_id,
                    config=server_config_dict,
                )
                continue

            # Проверяем обязательные поля
            name = server_config_dict.get("name")
            command = server_config_dict.get("command")
            if not name or not command:
                logger.warning(
                    "mcp_server_config_missing_name_or_command",
                    session_id=session_state.session_id,
                    config=server_config_dict,
                )
                continue

            try:
                # Преобразуем dict в MCPServerConfig
                config = MCPServerConfig(
                    name=name,
                    command=command,
                    args=server_config_dict.get("args", []),
                    env=server_config_dict.get("env", []),
                )

                # Добавляем сервер и получаем список инструментов
                tool_definitions = await mcp_manager.add_server(config)

                logger.info(
                    "mcp_server_initialized",
                    session_id=session_state.session_id,
                    server=name,
                    tools_count=len(tool_definitions),
                    tool_names=[td.name for td in tool_definitions],
                )

                # Получаем prompts от MCP сервера и регистрируем как slash-команды
                await self._register_mcp_prompts_as_slash_commands(
                    session_state, mcp_manager, name
                )

                # Отправляем initial available_commands_update клиенту
                await _on_mcp_tools_changed()

            except MCPManagerError as e:
                logger.error(
                    "failed_to_initialize_mcp_server",
                    session_id=session_state.session_id,
                    server=name,
                    error=str(e),
                )
            except Exception as e:
                logger.exception(
                    "unexpected_error_initializing_mcp_server",
                    session_id=session_state.session_id,
                    server=name,
                    error=str(e),
                )

    async def _register_mcp_prompts_as_slash_commands(
        self,
        session_state: SessionState,
        mcp_manager: MCPManager,
        server_name: str,
    ) -> None:
        """Регистрирует MCP prompts как slash-команды для сессии.

        Args:
            session_state: Состояние сессии для обновления available_commands.
            mcp_manager: Менеджер MCP серверов.
            server_name: Имя сервера для получения prompts.
        """
        try:
            all_prompts = await mcp_manager.get_all_prompts()
            server_prompts = all_prompts.get(server_name, [])

            if not server_prompts:
                logger.debug(
                    "no_prompts_from_mcp_server",
                    session_id=session_state.session_id,
                    server=server_name,
                )
                return

            # Регистрируем prompts (временно в session_state.mcp_prompt_handlers)
            self._register_mcp_prompts_from_list(
                session_state, mcp_manager, server_name, server_prompts
            )

            # Копируем handlers в runtime (основное хранилище)
            runtime = await self._runtime_registry.get(session_state.session_id)
            if runtime is not None:
                runtime.mcp_prompt_handlers.update(session_state.mcp_prompt_handlers)
                session_state.mcp_prompt_handlers.clear()
        except Exception as e:
            logger.warning(
                "failed_to_register_mcp_prompts_as_slash_commands",
                session_id=session_state.session_id,
                server=server_name,
                error=str(e),
            )

    def _register_mcp_prompts_from_list(
        self,
        session_state: SessionState,
        mcp_manager: MCPManager,
        server_name: str,
        server_prompts: list,
    ) -> None:
        """Регистрирует prompts из списка без повторного вызова get_all_prompts().

        Args:
            session_state: Состояние сессии для обновления available_commands.
            mcp_manager: Менеджер MCP серверов.
            server_name: Имя сервера.
            server_prompts: Список prompts для регистрации.
        """
        for prompt_def in server_prompts:
            # Формируем arguments_hint из аргументов prompt
            arguments_hint = None
            if prompt_def.arguments:
                arg_parts = []
                for arg in prompt_def.arguments:
                    if arg.required:
                        arg_parts.append(f"<{arg.name}>")
                    else:
                        arg_parts.append(f"[{arg.name}]")
                arguments_hint = " ".join(arg_parts)

            # Создаём handler для этого prompt
            from .handlers.slash_commands.builtin.mcp_prompt import MCPPromptCommandHandler

            handler = MCPPromptCommandHandler(
                server_id=server_name,
                prompt_name=prompt_def.name,
                mcp_manager=mcp_manager,
                description=prompt_def.title or prompt_def.description or prompt_def.name,
                arguments_hint=arguments_hint,
            )

            # Сохраняем handler в session_state (временное хранение)
            session_state.mcp_prompt_handlers[prompt_def.name] = handler

            # Добавляем определение команды в available_commands
            prompt_commands = mcp_prompts_to_available_commands([prompt_def])
            session_state.available_commands.extend(prompt_commands)

            logger.debug(
                "registered_mcp_prompt_as_slash_command",
                session_id=session_state.session_id,
                server=server_name,
                prompt=prompt_def.name,
            )

        logger.info(
            "registered_mcp_prompts_as_slash_commands",
            session_id=session_state.session_id,
            server=server_name,
            prompts_count=len(server_prompts),
        )

    async def _send_message(
        self,
        message: ACPMessage,
        session_id: str | None = None,
    ) -> None:
        """Публикует сообщение в notification bus.

        Args:
            message: Сообщение для публикации.
            session_id: ID сессии для получения bus. Если None, используется
                текущая сессия из контекста (если доступна).
        """
        if session_id is None:
            logger.warning(
                "cannot_publish_notification: no session_id",
                method=message.method,
            )
            return

        bus = await self._runtime_registry.get_notification_bus(session_id)
        await bus.publish(message)
