"""Узкая возможность «перечислить файлы проекта» (`project/list_files`).

ADR-009, раздел 6. Context Manager нуждается в перечислении файлов, а держал
**исполнение произвольной shell-команды**: три сырых вызова `terminal/*` с
литеральной командой в `gatherer.py`. Возможность заменяет широкое полномочие
узким — команду формирует один владелец (этот модуль), потребитель её не
передаёт, поэтому валидировать нечего и белый список команд не нужен.

Носитель остаётся терминалом сознательно: в ACP есть только `fs/read_text_file`
и `fs/write_text_file`, метода перечисления каталога нет, а прямой доступ к
файловой системе из агента запрещён — ACP отдаёт её клиенту. Терминал здесь —
**деталь реализации возможности**, а не полномочие потребителя: появится листинг
в спецификации — сменится реализация, а не вызывающие (порядок ADR-008 §5).

`kind="read"`: перечисление — это чтение, риск тот же, что у разрешённых чтений
внутри рабочего каталога. Побочно это верно и для plan-режима, где `execute`
блокируется, хотя ничего исполняющего по смыслу не происходит.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.tools.base import ToolDefinition, ToolExecutionResult

if TYPE_CHECKING:
    from codelab.server.domain.session import Session
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger()

LIST_FILES_TOOL = "project/list_files"

# Единственный владелец команды. Потребитель возможности её не видит и не
# передаёт — в этом вся разница с прежними тремя вызовами `terminal/*`.
_LIST_FILES_COMMAND = "find . -type f"


class ProjectToolDefinitions:
    """Возможности над проектом целиком, реализованные поверх терминала."""

    @staticmethod
    def list_files() -> ToolDefinition:
        """Определение `project/list_files`.

        `internal=True`: возможность существует для сборки контекста, а не для
        модели. У модели терминал уже есть, и предъявлять ей вторую дорогу к
        тому же означало бы сдвинуть набор инструментов в payload'е — то есть
        сбросить prompt cache без причины.
        """
        return ToolDefinition(
            name=LIST_FILES_TOOL,
            description=(
                "List files of the current project. Read-only enumeration: "
                "the command is fixed by the server and cannot be supplied by the caller."
            ),
            parameters={"type": "object", "properties": {}, "required": []},
            kind="read",
            requires_permission=True,
            internal=True,
        )

    @staticmethod
    def register_all(
        tool_registry: ToolRegistry,
        executor: Any,
    ) -> None:
        """Зарегистрировать возможность поверх терминального executor'а.

        Args:
            tool_registry: Реестр инструментов.
            executor: `TerminalToolExecutor` или обёртывающий его декоратор —
                тот же экземпляр, что обслуживает `terminal/*`: реестр alias'ов
                обязан быть один на процесс.
        """

        async def list_files_handler(session: Session, **_: Any) -> ToolExecutionResult:
            return await _list_files(session, executor)

        tool_registry.register(ProjectToolDefinitions.list_files(), list_files_handler)


async def _list_files(session: Session, executor: Any) -> ToolExecutionResult:
    """Перечислить файлы проекта: `create` → `wait_for_exit` → `release`.

    Освобождение — в `finally` и у создателя: без него реестр alias'ов растёт на
    каждое перечисление и уезжает на диск в каждой ревизии документа сессии
    (P2-58). Неудача освобождения не отменяет уже полученный результат.
    """
    terminal_id = ""
    try:
        create_result = await executor.execute(
            session,
            {
                "operation": "create",
                "command": _LIST_FILES_COMMAND,
                "cwd": session.config.cwd,
            },
        )
        if not create_result.success:
            return ToolExecutionResult(
                success=False,
                error=create_result.error or "Не удалось создать терминал для перечисления файлов",
            )

        terminal_id = _terminal_id_of(create_result)
        if not terminal_id:
            return ToolExecutionResult(
                success=False,
                error="Терминал перечисления файлов не вернул идентификатор",
            )

        wait_result = await executor.execute(
            session,
            {"operation": "wait_for_exit", "terminal_id": terminal_id},
        )
        if not wait_result.success:
            return ToolExecutionResult(
                success=False,
                error=wait_result.error or "Перечисление файлов не завершилось",
            )

        return ToolExecutionResult(
            success=True,
            output=wait_result.output or "",
            metadata={"command": _LIST_FILES_COMMAND},
        )
    finally:
        if terminal_id:
            await _release(session, executor, terminal_id)


def _terminal_id_of(result: ToolExecutionResult) -> str:
    """Идентификатор терминала из результата `create`."""
    if result.metadata:
        terminal_id = result.metadata.get("terminal_id", "")
        if terminal_id:
            return str(terminal_id)
    if result.raw_output:
        return str(result.raw_output.get("terminal_id", ""))
    return ""


async def _release(session: Session, executor: Any, terminal_id: str) -> None:
    """Освободить терминал, не роняя вызывающего."""
    try:
        result = await executor.execute(
            session,
            {"operation": "release", "terminal_id": terminal_id},
        )
        if not result.success:
            logger.debug(
                "project.list_files.release_failed",
                session_id=str(session.id),
                terminal_id=terminal_id,
                error=result.error,
            )
    except Exception:
        logger.exception(
            "project.list_files.release_error",
            session_id=str(session.id),
            terminal_id=terminal_id,
        )
