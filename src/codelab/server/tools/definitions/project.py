"""Узкие возможности над проектом: `project/list_files`, `project/search_content`.

ADR-009, раздел 6. Context Manager нуждается в перечислении файлов, а держал
**исполнение произвольной shell-команды**: три сырых вызова `terminal/*` с
литеральной командой в `gatherer.py`. Возможность заменяет широкое полномочие
узким — команду формирует один владелец (этот модуль), потребитель её не
передаёт, поэтому валидировать нечего и белый список команд не нужен.

Тем же разбором взят и поиск по содержимому (P2-57). Сборщику нужна одна
операция — «дай пути файлов, где встречается термин», — а в наличии была только
возможность прочитать **один** файл, и он собирал первую из второй сам: читал
окно из 30 файлов на каждый термин, искал подстроку в памяти, содержимое
выбрасывал. Замер прогонов 2026-08-17: 176 исполнений `fs/read_text_file` за
сборку, из них 137 обслужены кэшем, — то есть цена была не в диске, а в том, что
гейту разрешений предъявлялось 176 «чтений файла» вместо 5 «поисков», метрика
считала не ту величину, а окно `[:30]` — параметр реализации поиска — жило у
потребителя и делало хвост списка файлов невидимым для поиска вовсе.

Термин — единственный параметр возможности, и он единственное место, куда
попадает внешнее значение. Инъекции нет по построению, а не по экранированию:
`terminal/create` принимает `command` и `args` раздельно, поэтому термин уходит
элементом argv и shell его не разбирает.

Носитель остаётся терминалом сознательно: в ACP есть только `fs/read_text_file`
и `fs/write_text_file`, ни перечисления каталога, ни поиска в спецификации нет, а
прямой доступ к файловой системе из агента запрещён — ACP отдаёт её клиенту.
Терминал здесь — **деталь реализации возможности**, а не полномочие потребителя:
появятся эти методы в спецификации — сменится реализация, а не вызывающие
(порядок ADR-008 §5).

`kind="read"`: и перечисление, и поиск — это чтение, риск тот же, что у
разрешённых чтений внутри рабочего каталога. Побочно это верно и для plan-режима, где `execute`
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
SEARCH_CONTENT_TOOL = "project/search_content"

# Единственный владелец команд. Потребитель возможности их не видит и не
# передаёт — в этом вся разница с прежними тремя вызовами `terminal/*`.
_LIST_FILES_COMMAND = "find . -type f"
_SEARCH_COMMAND = "grep"

# `-r` — по всему дереву (области поиска у потребителя больше нет), `-l` — только
# пути, `-I` — пропустить двоичные, `-i -F` — регистронезависимое совпадение
# **подстроки**, ровно та семантика, что была у сравнения `term.lower() in
# content.lower()`. `--` закрывает список опций: термин, начинающийся с дефиса,
# остаётся термином.
_SEARCH_ARGS_PREFIX = ("-r", "-l", "-I", "-i", "-F", "--")

# grep: 0 — совпадения есть, 1 — совпадений нет, >=2 — «произошла ошибка».
# Штатны оба первых: «ничего не нашлось» — это результат, а не отказ.
_GREP_BENIGN_EXIT_CODES = frozenset({0, 1})

# «Ошибка» у grep включает любой нечитаемый файл — на живом проекте это норма
# (сокет `.codegraph/daemon.sock`, каталог без прав), и совпадения при этом уже
# найдены и напечатаны. Поэтому код возврата решает судьбу вызова только при
# пустом выводе: непустой вывод — это результат, пусть и неполный.
_FIND_BENIGN_EXIT_CODES = frozenset({0})


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
    def search_content() -> ToolDefinition:
        """Определение `project/search_content`.

        `internal=True` и `kind="read"` по тем же причинам, что у перечисления:
        поиск существует для сборки контекста, а не для модели, и по риску он
        равен разрешённым чтениям внутри рабочего каталога.
        """
        return ToolDefinition(
            name=SEARCH_CONTENT_TOOL,
            description=(
                "Find project files containing the given term. Read-only search: "
                "the command is fixed by the server, the caller supplies only the term."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Literal, case-insensitive substring to look for",
                    },
                },
                "required": ["term"],
            },
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

        async def search_content_handler(
            session: Session, **arguments: Any
        ) -> ToolExecutionResult:
            return await _search_content(session, executor, arguments.get("term"))

        tool_registry.register(ProjectToolDefinitions.list_files(), list_files_handler)
        tool_registry.register(ProjectToolDefinitions.search_content(), search_content_handler)


async def _list_files(session: Session, executor: Any) -> ToolExecutionResult:
    """Перечислить файлы проекта."""
    return await _run(
        session,
        executor,
        command=_LIST_FILES_COMMAND,
        args=None,
        purpose="перечисления файлов",
        benign_exit_codes=_FIND_BENIGN_EXIT_CODES,
    )


async def _search_content(session: Session, executor: Any, term: Any) -> ToolExecutionResult:
    """Найти файлы, содержащие термин.

    Отсутствие совпадений — успех с пустым выводом, а не отказ: иначе
    потребитель не отличит «в проекте нет такого» от «поиск сломался» и стал бы
    трактовать первое как второе. По той же причине штатен и код 2 при непустом
    выводе: у grep «ошибка» — это любой нечитаемый файл, а совпадения к этому
    моменту уже найдены.
    """
    if not isinstance(term, str) or not term.strip():
        return ToolExecutionResult(
            success=False,
            error="Параметр 'term' обязателен и не может быть пустым.",
        )

    return await _run(
        session,
        executor,
        command=_SEARCH_COMMAND,
        args=[*_SEARCH_ARGS_PREFIX, term, "."],
        purpose="поиска по содержимому",
        benign_exit_codes=_GREP_BENIGN_EXIT_CODES,
    )


async def _run(
    session: Session,
    executor: Any,
    *,
    command: str,
    args: list[str] | None,
    purpose: str,
    benign_exit_codes: frozenset[int],
) -> ToolExecutionResult:
    """Выполнить команду возможности: `create` → `wait_for_exit` → `release`.

    Освобождение — в `finally` и у создателя: без него реестр alias'ов растёт на
    каждый вызов и уезжает на диск в каждой ревизии документа сессии (P2-58).
    Неудача освобождения не отменяет уже полученный результат.

    **Успех определяется выводом, а не только кодом возврата.** Первый живой
    прогон показал, почему: `grep` вернул 2 («произошла ошибка») из-за одного
    нечитаемого сокета в дереве, уже напечатав найденный файл, — и весь результат
    выбрасывался. Код возврата решает исход лишь тогда, когда выводить нечего.

    Args:
        benign_exit_codes: Коды, штатные для этой команды. Их знает владелец
            команды: у `grep` таких два (0 и 1), потому что «не нашлось» — это
            результат.
    """
    terminal_id = ""
    try:
        create_arguments: dict[str, Any] = {
            "operation": "create",
            "command": command,
            "cwd": session.config.cwd,
        }
        if args is not None:
            create_arguments["args"] = args

        create_result = await executor.execute(session, create_arguments)
        if not create_result.success:
            return ToolExecutionResult(
                success=False,
                error=create_result.error or f"Не удалось создать терминал для {purpose}",
            )

        terminal_id = _terminal_id_of(create_result)
        if not terminal_id:
            return ToolExecutionResult(
                success=False,
                error=f"Терминал {purpose} не вернул идентификатор",
            )

        wait_result = await executor.execute(
            session,
            {"operation": "wait_for_exit", "terminal_id": terminal_id},
        )
        exit_code = _exit_code_of(wait_result)
        output = wait_result.output or ""

        # `wait_result.success` — это `exit_code == 0` у исполнителя; он же
        # единственный признак, если клиент кода возврата не вернул вовсе.
        if wait_result.success or exit_code in benign_exit_codes:
            return ToolExecutionResult(
                success=True,
                output=output,
                metadata={"command": command, "exit_code": exit_code},
            )

        if output.strip():
            # Часть дерева осталась непрочитанной, но найденное уже напечатано.
            # Диагностику утилиты потребитель отбрасывает при разборе, поэтому
            # неполный результат честнее пустого отказа — и он именуется неполным.
            logger.warning(
                "project.command.partial",
                session_id=str(session.id),
                command=command,
                args=args,
                exit_code=exit_code,
                output_preview=output[:200],
            )
            return ToolExecutionResult(
                success=True,
                output=output,
                metadata={"command": command, "exit_code": exit_code, "partial": True},
            )

        # Что именно было отправлено, знает только владелец возможности:
        # вызывающий передал термин, а не команду, и по его логу не восстановить,
        # с какими аргументами она ушла клиенту.
        logger.warning(
            "project.command.failed",
            session_id=str(session.id),
            command=command,
            args=args,
            exit_code=exit_code,
            error=wait_result.error,
        )
        reason = wait_result.error or f"Команда {purpose} завершилась с ошибкой"
        return ToolExecutionResult(
            success=False,
            error=f"{reason} (exit_code={exit_code})",
            metadata={"command": command, "exit_code": exit_code},
        )
    finally:
        if terminal_id:
            await _release(session, executor, terminal_id)


def _exit_code_of(result: ToolExecutionResult) -> int | None:
    """Код возврата из результата `wait_for_exit`."""
    for source in (result.metadata, result.raw_output):
        if source:
            exit_code = source.get("exit_code")
            if isinstance(exit_code, int):
                return exit_code
    return None


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
                "project.terminal.release_failed",
                session_id=str(session.id),
                terminal_id=terminal_id,
                error=result.error,
            )
    except Exception:
        logger.exception(
            "project.terminal.release_error",
            session_id=str(session.id),
            terminal_id=terminal_id,
        )
