"""Executor для терминальных операций через ClientRPC."""

from __future__ import annotations

from typing import Any

import structlog

from codelab.server.client_rpc import ClientRPCCancelledError
from codelab.server.domain.session import Session
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.base import ToolExecutor
from codelab.server.tools.executors.terminal_alias_registry import TerminalAliasRegistry
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge
from codelab.server.tools.integrations.permission_checker import PermissionChecker

logger = structlog.get_logger()


class TerminalToolExecutor(ToolExecutor):
    """Executor для терминальных операций через ClientRPC.

    Поддерживает:
    - terminal/create (запуск команды)
    - terminal/wait_for_exit (ожидание завершения)
    - terminal/release (освобождение терминала)

    Интегрирует проверку разрешений, логирование и lifecycle management.

    **Экземпляр обязан быть один на процесс.** С ADR-007 (шаг A) он владеет реестром
    alias'ов терминалов, а тот больше не персистится: второй экземпляр означал бы
    второй реестр, и alias, выданный одним, не разрешался бы другим. Сегодня это
    обеспечено конструктивно — единственная точка создания
    (`PromptOrchestrator._register_tool_executors`) сама живёт в `Scope.APP` и
    защищена флагом `_tools_registered`. Если точек станет больше, реестр надо
    поднять в DI-провайдер `Scope.APP`, как `TurnCancellationRegistry`.
    """

    def __init__(
        self,
        client_rpc_bridge: ClientRPCBridge,
        permission_checker: PermissionChecker,
    ) -> None:
        """Инициализировать executor с зависимостями.

        Args:
            client_rpc_bridge: Адаптер для ClientRPCService.
            permission_checker: Адаптер для PermissionManager.
        """
        self._bridge = client_rpc_bridge
        self._permission_checker = permission_checker
        self._aliases = TerminalAliasRegistry()

    def _resolve_terminal(
        self,
        session: Session,
        alias: str,
    ) -> tuple[str | None, ToolExecutionResult | None]:
        """Разрешает alias LLM в настоящий client terminalId.

        Возвращает ``(client_terminal_id, None)`` при успехе либо
        ``(None, error_result)`` с готовым failed-результатом, если alias
        неизвестен. Промах логируется как ошибка контракта (а не warning):
        LLM оперирует коротким alias, поэтому промах означает галлюцинацию id
        или обращение к уже освобождённому терминалу.
        """
        client_terminal_id = self._aliases.resolve(session, alias)
        if client_terminal_id is not None:
            return client_terminal_id, None

        known = self._aliases.known_aliases(session)
        # warning, а не error: промах по alias — галлюцинация модели, сервер отработал
        # верно и вернул модели список доступных терминалов. Уровень error здесь ломал
        # критерий «0 ошибок за прогон» (tech-debt P2-37).
        logger.warning(
            "terminal_alias_not_found",
            session_id=str(session.id),
            alias=alias,
            known_aliases=known,
        )
        available = ", ".join(known) if known else "нет активных терминалов"
        return None, ToolExecutionResult(
            success=False,
            error=f"Неизвестный терминал '{alias}'. Доступные терминалы: {available}.",
        )

    async def execute(
        self,
        session: Session,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить инструмент на основе аргументов.

        Args:
            session: Состояние сессии.
            arguments: Словарь аргументов инструмента.
                Ожидается поле 'operation' для выбора метода.

        Returns:
            ToolExecutionResult с результатом выполнения.
        """
        operation = arguments.get("operation")

        if operation == "create":
            return await self.execute_create(
                session=session,
                command=arguments.get("command", ""),
                args=arguments.get("args"),
                env=arguments.get("env"),
                cwd=arguments.get("cwd"),
                output_byte_limit=arguments.get("output_byte_limit"),
            )
        elif operation == "wait_for_exit":
            return await self.execute_wait_for_exit(
                session=session,
                terminal_id=arguments.get("terminal_id", ""),
            )
        elif operation == "release":
            return await self.execute_release(
                session=session,
                terminal_id=arguments.get("terminal_id", ""),
            )
        else:
            return ToolExecutionResult(
                success=False,
                error=f"Неизвестная операция: {operation}",
            )

    async def execute_create(
        self,
        session: Session,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        output_byte_limit: int | None = None,
    ) -> ToolExecutionResult:
        """Создать терминал и запустить команду через ClientRPC.

        Args:
            session: Состояние сессии.
            command: Команда для выполнения.
            args: Аргументы команды (опционально).
            env: Переменные окружения (опционально).
            cwd: Рабочая директория (опционально).
            output_byte_limit: Лимит байт output (опционально).

        Returns:
            ToolExecutionResult с terminal_id в metadata.
        """
        try:
            logger.debug(
                "Начало выполнения terminal/create",
                extra={
                    "session_id": str(session.id),
                    "command": command,
                    "cwd": cwd,
                },
            )

            # Примечание: Проверка разрешений выполняется в
            # PromptOrchestrator._decide_tool_execution() перед вызовом executor.
            # Здесь мы только выполняем операцию.

            # Вызов ClientRPC для создания терминала
            client_terminal_id = await self._bridge.create_terminal(
                session=session,
                command=command,
                args=args,
                env=env,
                cwd=cwd,
                output_byte_limit=output_byte_limit,
            )

            if client_terminal_id is None:
                return ToolExecutionResult(
                    success=False,
                    error=f"Ошибка при создании терминала для команды: {command}",
                )

            # LLM оперирует коротким alias (см. tech-debt #18), а клиент — своим
            # родным id. Регистрируем маппинг и отдаём наружу alias.
            alias = self._aliases.register(session, client_terminal_id)

            logger.debug(
                "Терминал успешно создан",
                extra={
                    "session_id": str(session.id),
                    "terminal_id": alias,
                    "client_terminal_id": client_terminal_id,
                    "command": command,
                },
            )

            # Формируем ToolCallContent items для ACP (10-Terminal.md: Embedding in Tool Calls)
            # Terminal content идёт первым — клиент может сразу начать отображение
            # (адресуется СВОИМ terminalId). Text content — fallback для LLM (alias).
            content_items = [
                {
                    "type": "terminal",
                    "terminalId": client_terminal_id,
                },
                {
                    "type": "content",
                    "content": {
                        "type": "text",
                        "text": f"Terminal {alias} created for command: {command}",
                    },
                },
            ]

            return ToolExecutionResult(
                success=True,
                output=f"Терминал создан с ID: {alias}",
                metadata={
                    "terminal_id": alias,
                    "command": command,
                },
                raw_output={
                    "terminal_id": alias,
                },
                content=content_items,
            )

        except ClientRPCCancelledError as e:
            # Отмена turn'а пользователем — не сбой инструмента: статус вызова
            # `cancelled`, и модель получает правдивый текст, а не «Ошибка»
            # (tech-debt P2-50).
            logger.info(
                "client_rpc_cancelled",
                operation="создания терминала",
                reason=str(e),
            )
            return ToolExecutionResult(
                success=False,
                cancelled=True,
                error="Создание терминала отменено пользователем",
            )

        except Exception as e:
            logger.error(
                "Ошибка при создании терминала",
                extra={
                    "session_id": str(session.id),
                    "command": command,
                    "error": str(e),
                },
            )
            return ToolExecutionResult(
                success=False,
                error=f"Ошибка при создании терминала: {str(e)}",
            )

    async def execute_wait_for_exit(
        self,
        session: Session,
        terminal_id: str,
    ) -> ToolExecutionResult:
        """Ожидать завершения терминала через ClientRPC.

        По ACP spec terminal/wait_for_exit возвращает только exitCode/signal.
        Output получается через отдельный вызов terminal/output.

        Args:
            session: Состояние сессии.
            terminal_id: ID терминала.

        Returns:
            ToolExecutionResult с exit_code и output.
        """
        try:
            logger.debug(
                "Начало выполнения terminal/wait_for_exit",
                extra={
                    "session_id": str(session.id),
                    "terminal_id": terminal_id,
                },
            )

            client_terminal_id, error_result = self._resolve_terminal(session, terminal_id)
            if error_result is not None:
                return error_result
            assert client_terminal_id is not None  # resolve вернул id, раз нет ошибки

            # 1. Сначала пытаемся получить текущий output и статус
            output_data = await self._bridge.terminal_output(
                session=session,
                terminal_id=client_terminal_id,
            )

            output = ""
            exit_code: int | None = -1
            signal: str | None = None

            if output_data:
                output = output_data.get("output", "")
                is_complete = output_data.get("is_complete", False)
                exit_code = output_data.get("exit_code")
                signal = output_data.get("signal")

                # Если терминал уже завершён — не нужно ждать
                if is_complete and (exit_code is not None or signal is not None):
                    logger.debug(
                        "Терминал уже завершён (получено из terminal/output)",
                        extra={
                            "session_id": str(session.id),
                            "terminal_id": terminal_id,
                            "exit_code": exit_code,
                        },
                    )
                    return ToolExecutionResult(
                        success=(exit_code == 0) if exit_code is not None else False,
                        output=output,
                        metadata={
                            "terminal_id": terminal_id,
                            "exit_code": exit_code,
                            "signal": signal,
                        },
                        raw_output={
                            "exit_code": exit_code,
                            "signal": signal,
                            "output": output,
                        },
                    )

            # 2. Если ещё не завершён — ждём через wait_for_exit
            wait_result = await self._bridge.wait_terminal_exit(
                session=session,
                terminal_id=client_terminal_id,
            )

            if wait_result is None:
                return ToolExecutionResult(
                    success=False,
                    error=f"Ошибка при ожидании завершения терминала: {terminal_id}",
                )

            exit_code = wait_result.get("exit_code")
            signal = wait_result.get("signal")

            # 3. После завершения — получаем финальный output
            final_output_data = await self._bridge.terminal_output(
                session=session,
                terminal_id=client_terminal_id,
            )
            if final_output_data:
                output = final_output_data.get("output", "")

            resolved_exit_code = exit_code if exit_code is not None else -1

            logger.debug(
                "Терминал завершен",
                extra={
                    "session_id": str(session.id),
                    "terminal_id": terminal_id,
                    "exit_code": resolved_exit_code,
                    "signal": signal,
                },
            )

            return ToolExecutionResult(
                success=resolved_exit_code == 0,
                output=output,
                metadata={
                    "terminal_id": terminal_id,
                    "exit_code": resolved_exit_code,
                    "signal": signal,
                },
                raw_output={
                    "exit_code": resolved_exit_code,
                    "signal": signal,
                    "output": output,
                },
            )

        except ClientRPCCancelledError as e:
            # Отмена turn'а пользователем — не сбой инструмента: статус вызова
            # `cancelled`, и модель получает правдивый текст, а не «Ошибка»
            # (tech-debt P2-50).
            logger.info(
                "client_rpc_cancelled",
                operation="ожидания завершения терминала",
                terminal_id=terminal_id,
                reason=str(e),
            )
            return ToolExecutionResult(
                success=False,
                cancelled=True,
                error=(
                    "Ожидание завершения терминала отменено пользователем: "
                    f"{terminal_id}"
                ),
            )

        except Exception as e:
            logger.error(
                "Ошибка при ожидании завершения терминала",
                extra={
                    "session_id": str(session.id),
                    "terminal_id": terminal_id,
                    "error": str(e),
                },
            )
            return ToolExecutionResult(
                success=False,
                error=f"Ошибка при ожидании завершения терминала: {str(e)}",
            )

    async def execute_release(
        self,
        session: Session,
        terminal_id: str,
    ) -> ToolExecutionResult:
        """Освободить терминал через ClientRPC.

        Args:
            session: Состояние сессии.
            terminal_id: ID терминала.

        Returns:
            ToolExecutionResult с результатом освобождения.
        """
        try:
            logger.debug(
                "Начало выполнения terminal/release",
                extra={
                    "session_id": str(session.id),
                    "terminal_id": terminal_id,
                },
            )

            client_terminal_id, error_result = self._resolve_terminal(session, terminal_id)
            if error_result is not None:
                return error_result
            assert client_terminal_id is not None  # resolve вернул id, раз нет ошибки

            # Вызов ClientRPC для освобождения терминала
            success = await self._bridge.release_terminal(
                session=session,
                terminal_id=client_terminal_id,
            )

            if not success:
                return ToolExecutionResult(
                    success=False,
                    error=f"Ошибка при освобождении терминала: {terminal_id}",
                )

            # Терминал освобождён — снимаем alias, чтобы повторные обращения
            # получали внятную ошибку контракта, а не промах по client id.
            self._aliases.release(session, terminal_id)

            logger.debug(
                "Терминал успешно освобожден",
                extra={
                    "session_id": str(session.id),
                    "terminal_id": terminal_id,
                },
            )

            return ToolExecutionResult(
                success=True,
                output=f"Терминал {terminal_id} успешно освобожден",
                metadata={
                    "terminal_id": terminal_id,
                },
            )

        except ClientRPCCancelledError as e:
            # Отмена turn'а пользователем — не сбой инструмента: статус вызова
            # `cancelled`, и модель получает правдивый текст, а не «Ошибка»
            # (tech-debt P2-50).
            logger.info(
                "client_rpc_cancelled",
                operation="освобождения терминала",
                terminal_id=terminal_id,
                reason=str(e),
            )
            return ToolExecutionResult(
                success=False,
                cancelled=True,
                error=f"Освобождение терминала отменено пользователем: {terminal_id}",
            )

        except Exception as e:
            logger.error(
                "Ошибка при освобождении терминала",
                extra={
                    "session_id": str(session.id),
                    "terminal_id": terminal_id,
                    "error": str(e),
                },
            )
            return ToolExecutionResult(
                success=False,
                error=f"Ошибка при освобождении терминала: {str(e)}",
            )
