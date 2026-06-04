"""Handler для MCP Prompts как slash commands.

Позволяет вызывать MCP prompts через slash commands.
При вызове /prompt_name arg1 arg2 вызывает mcp_manager.get_prompt()
и возвращает сообщения промпта как контент.

Согласовано с:
- MCP spec: prompts/get
- ACP spec: 14-Slash Commands
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from codelab.server.models import AvailableCommand, AvailableCommandInput

from ..base import CommandHandler, CommandResult

if TYPE_CHECKING:
    from codelab.server.mcp.manager import MCPManager
    from codelab.server.protocol.state import SessionState

logger = logging.getLogger(__name__)


class MCPPromptCommandHandler(CommandHandler):
    """Handler для MCP prompt как slash-команды.

    При вызове команды:
    1. Парсит аргументы из args
    2. Вызывает mcp_manager.get_prompt(server_id, name, arguments)
    3. Возвращает messages из промпта как CommandResult.content

    Пример использования:
        handler = MCPPromptCommandHandler(
            server_id="mcp-server-1",
            prompt_name="code-review",
            mcp_manager=mcp_manager,
            description="Review code for best practices",
            arguments_hint="<language> [style]",
        )
        result = handler.execute(["python", "pep8"], session)
    """

    def __init__(
        self,
        server_id: str,
        prompt_name: str,
        mcp_manager: MCPManager,
        description: str,
        arguments_hint: str | None = None,
    ) -> None:
        """Инициализирует handler для MCP prompt.

        Args:
            server_id: ID MCP сервера, предоставляющего prompt
            prompt_name: Имя prompt на MCP сервере
            mcp_manager: Менеджер MCP серверов
            description: Описание команды для клиента
            arguments_hint: Подсказка по аргументам (например, "<lang> [style]")
        """
        self._server_id = server_id
        self._prompt_name = prompt_name
        self._mcp_manager = mcp_manager
        self._description = description
        self._arguments_hint = arguments_hint

    def execute(
        self,
        args: list[str],
        session: SessionState,
    ) -> CommandResult:
        """Выполняет команду — вызывает MCP prompt.

        Args:
            args: Аргументы команды (позиционные, для заполнения prompt arguments)
            session: Состояние сессии

        Returns:
            CommandResult с сообщениями из MCP prompt
        """
        # Получаем prompt definition для маппинга аргументов
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Если уже в async контексте, создаём task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = loop.run_in_executor(
                        pool,
                        self._execute_sync,
                        args,
                    )
                    # Для простоты — синхронный вызов через run_until_complete
                    # В реальном коде нужно использовать async execute
                    return self._execute_sync(args)
            else:
                return loop.run_until_complete(self._execute_async(args))
        except RuntimeError:
            # Нет event loop — используем sync версию
            return self._execute_sync(args)

    def _execute_sync(self, args: list[str]) -> CommandResult:
        """Синхронное выполнение (fallback)."""
        # Для синхронного вызова возвращаем ошибку — нужен async контекст
        return CommandResult(
            content=[{
                "type": "text",
                "text": f"⚠️ MCP prompt '{self._prompt_name}' требует async контекст.",
            }],
            stop_reason="end_turn",
        )

    async def execute_async(
        self,
        args: list[str],
        session: SessionState,
    ) -> CommandResult:
        """Async версия execute — основной метод.

        Args:
            args: Аргументы команды
            session: Состояние сессии

        Returns:
            CommandResult с сообщениями из MCP prompt
        """
        return await self._execute_async(args)

    async def _execute_async(self, args: list[str]) -> CommandResult:
        """Внутренний async метод выполнения."""
        try:
            # Получаем список prompts для маппинга имён аргументов
            all_prompts = await self._mcp_manager.get_all_prompts()
            server_prompts = all_prompts.get(self._server_id, [])
            prompt_def = next(
                (p for p in server_prompts if p.name == self._prompt_name),
                None,
            )

            # Маппим позиционные args в именованные arguments
            arguments = self._map_arguments(args, prompt_def)

            # Вызываем MCP prompt
            result = await self._mcp_manager.get_prompt(
                server_id=self._server_id,
                name=self._prompt_name,
                arguments=arguments,
            )

            # Конвертируем messages в content blocks
            content = self._convert_messages_to_content(result.messages)

            return CommandResult(
                content=content,
                stop_reason="end_turn",
            )

        except Exception as e:
            logger.error(
                "Failed to execute MCP prompt '%s' from '%s': %s",
                self._prompt_name,
                self._server_id,
                e,
            )
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": f"❌ Ошибка при вызове MCP prompt '{self._prompt_name}': {e}",
                }],
                stop_reason="end_turn",
            )

    def _map_arguments(
        self,
        args: list[str],
        prompt_def: Any,
    ) -> dict[str, str] | None:
        """Маппит позиционные аргументы в именованные.

        Args:
            args: Позиционные аргументы из команды
            prompt_def: Определение prompt с аргументами

        Returns:
            Словарь {argument_name: value} или None
        """
        if not args or prompt_def is None or not prompt_def.arguments:
            return None

        arguments: dict[str, str] = {}
        for i, arg_value in enumerate(args):
            if i < len(prompt_def.arguments):
                arg_name = prompt_def.arguments[i].name
                arguments[arg_name] = arg_value

        return arguments if arguments else None

    def _convert_messages_to_content(
        self,
        messages: list[Any],
    ) -> list[dict[str, Any]]:
        """Конвертирует MCP messages в ACP content blocks.

        Args:
            messages: Список сообщений из MCPGetPromptResult

        Returns:
            Список content blocks для CommandResult
        """
        content: list[dict[str, Any]] = []

        for msg in messages:
            # msg может быть dict или MCPPromptMessage
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                msg_content = msg.get("content", {})
            else:
                role = msg.role
                msg_content = msg.content

            # Извлекаем текст из content
            if isinstance(msg_content, dict):
                text = msg_content.get("text", "")
            else:
                text = str(msg_content)

            # Форматируем с указанием роли
            if role == "assistant":
                content.append({"type": "text", "text": text})
            else:
                # user messages — как контекст
                content.append({
                    "type": "text",
                    "text": f"**User:** {text}",
                })

        return content

    def get_definition(self) -> AvailableCommand:
        """Возвращает определение команды для регистрации."""
        input_spec = None
        if self._arguments_hint:
            input_spec = AvailableCommandInput(hint=self._arguments_hint)

        return AvailableCommand(
            name=self._prompt_name,
            description=self._description,
            input=input_spec,
        )
