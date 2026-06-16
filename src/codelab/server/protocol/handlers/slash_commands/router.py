"""Маршрутизатор slash commands.

SlashCommandRouter направляет slash-команды к соответствующим handlers
и возвращает результат в формате ProtocolOutcome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.protocol.state import ProtocolOutcome
from codelab.shared.messages import ACPMessage

from .base import CommandResult
from .registry import CommandRegistry

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()


class SlashCommandRouter:
    """Маршрутизатор slash-команд к обработчикам.

    Принимает распарсенную slash-команду и направляет её к соответствующему
    handler'у из CommandRegistry или к MCP prompt handler'у.
    Если handler не найден, возвращает None для fallback обработки
    (например, отправки в LLM).

    Пример использования:
        router = SlashCommandRouter(registry)
        result = await router.route("status", [], session)
        if result is not None:
            # Команда обработана
            return result
        else:
            # Fallback: отправить в LLM
            ...
    """

    def __init__(self, registry: CommandRegistry) -> None:
        """Инициализирует роутер с реестром команд.

        Args:
            registry: Реестр команд с handlers
        """
        self._registry = registry

    async def route(
        self,
        command: str,
        args: list[str],
        session: SessionState,
        mcp_prompt_handlers: dict[str, Any] | None = None,
    ) -> ProtocolOutcome | None:
        """Маршрутизирует команду к handler'у.

        Сначала ищет handler в CommandRegistry (встроенные команды).
        Если не найден, проверяет mcp_prompt_handlers (MCP prompts).

        Args:
            command: Имя команды (без слеша)
            args: Аргументы команды
            session: Текущее состояние сессии
            mcp_prompt_handlers: Обработчики MCP prompts из runtime registry

        Returns:
            ProtocolOutcome с результатом или None для fallback
        """
        # Сначала проверяем встроенные команды в registry
        handler = self._registry.get_handler(command)

        if handler is not None:
            logger.info(
                "Routing slash command to handler",
                command=command,
                args=args,
                session_id=session.session_id,
            )

            try:
                # Для help команды передаём mcp_prompt_handlers
                execute_fn = getattr(handler, "execute_with_handlers", None)
                if command == "help" and execute_fn is not None:
                    result = execute_fn(args, session, mcp_prompt_handlers or {})
                else:
                    result = handler.execute(args, session)
                return self._build_outcome(result, session)
            except Exception as e:
                logger.exception(
                    "Slash command execution failed",
                    command=command,
                    error=str(e),
                )
                return self._build_error_outcome(command, str(e), session)

        # Проверяем MCP prompt handlers из runtime registry
        handlers = mcp_prompt_handlers or {}
        mcp_handler = handlers.get(command)
        if mcp_handler is not None:
            logger.info(
                "Routing MCP prompt slash command",
                command=command,
                args=args,
                session_id=session.session_id,
            )

            try:
                # MCPPromptCommandHandler имеет async execute_async
                result = await mcp_handler.execute_async(args, session)
                return self._build_outcome(result, session)
            except Exception as e:
                logger.exception(
                    "MCP prompt slash command execution failed",
                    command=command,
                    error=str(e),
                )
                return self._build_error_outcome(command, str(e), session)

        logger.debug(
            "No handler for slash command, falling back",
            command=command,
            session_id=session.session_id,
        )
        return None

    def _build_outcome(
        self,
        result: CommandResult,
        session: SessionState,
    ) -> ProtocolOutcome:
        """Строит ProtocolOutcome из CommandResult.

        Args:
            result: Результат выполнения команды
            session: Состояние сессии

        Returns:
            ProtocolOutcome с сообщениями для отправки клиенту
        """
        messages: list[ACPMessage] = []

        # Добавляем дополнительные updates (например, mode_update)
        for update in result.updates:
            messages.append(
                ACPMessage.notification(
                    "session/update",
                    {
                        "sessionId": session.session_id,
                        "update": update,
                    },
                )
            )

        # Добавляем основной контент как agent_message_chunk для отображения в UI
        # Клиент ожидает sessionUpdate: "agent_message_chunk" с content block
        for content_block in result.content:
            messages.append(
                ACPMessage.notification(
                    "session/update",
                    {
                        "sessionId": session.session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": content_block,
                        },
                    },
                )
            )

        return ProtocolOutcome(notifications=messages)

    def _build_error_outcome(
        self,
        command: str,
        error: str,
        session: SessionState,
    ) -> ProtocolOutcome:
        """Строит ProtocolOutcome для ошибки выполнения.

        Args:
            command: Имя команды
            error: Текст ошибки
            session: Состояние сессии

        Returns:
            ProtocolOutcome с сообщением об ошибке
        """
        error_content = {
            "type": "text",
            "text": f"❌ Ошибка выполнения команды /{command}: {error}",
        }

        return ProtocolOutcome(
            notifications=[
                ACPMessage.notification(
                    "session/update",
                    {
                        "sessionId": session.session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": error_content,
                        },
                    },
                )
            ]
        )

    @property
    def registry(self) -> CommandRegistry:
        """Возвращает реестр команд."""
        return self._registry
