"""Простая реализация реестра инструментов для системы tools."""

import inspect
from collections.abc import Callable
from typing import Any

import structlog

from codelab.server.agent.contracts.ports import writable_session
from codelab.server.domain.path_boundary import (
    is_inside_cwd,
    normalize_path,
    outside_cwd_error,
)
from codelab.server.domain.value_objects import ToolInvocationSubject
from codelab.server.tools.base import ToolDefinition, ToolExecutionResult, ToolRegistry
from codelab.server.tools.mapping import acp_name_to_llm_name, llm_name_to_acp_name

# Используем structlog для структурированного логирования
logger = structlog.get_logger()

# Команда терминала — единственный аргумент, для которого граница пути неприменима:
# она исполняется целиком. В замере ADR-009 её видно отдельно от файловых путей.
_COMMAND_KEYS = ("command", "cmd")


def _command_preview(arguments: dict[str, Any]) -> str | None:
    """Начало команды терминала — чтобы в замере отличать `find` от произвольного."""
    if not isinstance(arguments, dict):
        return None
    for key in _COMMAND_KEYS:
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return value[:120]
    return None


def session_id_of(session: Any) -> str | None:
    """Идентификатор сессии, если он доступен: замер не вправе требовать сессию."""
    session_id = getattr(session, "id", None)
    return str(session_id) if session_id is not None else None


class SimpleToolRegistry(ToolRegistry):
    """Простой реестр инструментов с хранением в памяти.

    Хранит определения инструментов и их обработчики (handlers).
    Позволяет регистрировать, получать и выполнять инструменты.
    """

    def __init__(self) -> None:
        """Инициализация реестра."""
        # Словарь для хранения определений инструментов
        self._tools: dict[str, ToolDefinition] = {}
        # Словарь для хранения обработчиков инструментов
        self._handlers: dict[str, Callable] = {}

    def register(
        self,
        tool: ToolDefinition,
        handler: Callable,
    ) -> None:
        """Регистрация инструмента и его обработчика.

        Args:
            tool: Определение инструмента (ToolDefinition)
            handler: Callable обработчик инструмента

        Raises:
            ValueError: Если имя инструмента пустое
        """
        # Проверка, что имя инструмента не пустое
        if not tool.name or not tool.name.strip():
            raise ValueError("Имя инструмента не может быть пустым")

        # Регистрация инструмента и его обработчика
        self._tools[tool.name] = tool
        self._handlers[tool.name] = handler

    def get(self, name: str) -> ToolDefinition | None:
        """Получение определения инструмента по имени.

        Args:
            name: Имя инструмента

        Returns:
            Определение инструмента или None, если не найден
        """
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """Получение списка всех зарегистрированных инструментов.

        Returns:
            Список определений инструментов
        """
        return list(self._tools.values())

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнение инструмента по имени с переданными аргументами.

        Args:
            name: Имя инструмента
            arguments: Словарь аргументов для обработчика

        Returns:
            Результат выполнения (ToolExecutionResult)

        Raises:
            ValueError: Если инструмент не найден
        """
        # Проверка существования инструмента
        if name not in self._tools:
            return ToolExecutionResult(
                success=False,
                error=f"Инструмент '{name}' не найден в реестре",
            )

        # Получение обработчика
        handler = self._handlers[name]

        try:
            # Выполнение обработчика с аргументами
            output = handler(**arguments)

            # Преобразование вывода в строку если необходимо
            output_str = str(output) if output is not None else None

            return ToolExecutionResult(
                success=True,
                output=output_str,
            )
        except Exception as exc:
            # Обработка исключений при выполнении
            error_msg = f"Ошибка при выполнении инструмента '{name}': {str(exc)}"
            return ToolExecutionResult(
                success=False,
                error=error_msg,
            )

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        kind: str,
        executor: Callable,
        requires_permission: bool = True,
    ) -> None:
        """Регистрация инструмента через интерфейс ToolRegistry."""
        tool = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            kind=kind,
            requires_permission=requires_permission,
        )
        self.register(tool, executor)

    def get_available_tools(
        self,
        session_id: str,
        include_permission_required: bool = True,
    ) -> list[ToolDefinition]:
        """Получить доступные инструменты для сессии.

        В упрощенной реализации возвращает все инструменты.
        """
        # Внутренние возможности модели не предъявляются: они существуют для
        # сборки контекста (ADR-009, раздел 6).
        tools = [t for t in self._tools.values() if not t.internal]
        if not include_permission_required:
            tools = [t for t in tools if not t.requires_permission]
        return tools

    def to_llm_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """Преобразовать определения инструментов для OpenAI API.

        Применяет маппинг имён: ACP имена (с `/`) конвертируются
        в LLM-совместимые имена (с `_`).

        Формат соответствует OpenAI API:
        {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": acp_name_to_llm_name(tool.name),
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _probe_invocation(
        self,
        acp_tool_name: str,
        arguments: dict[str, Any],
        session: Any,
        subject: ToolInvocationSubject,
    ) -> None:
        """Замер авторизации инвокации — шаг 0 ADR-009, решений не принимает.

        Отвечает на вопрос, который нельзя снять задним числом: **что именно и от
        чьего имени исполняется мимо гейта разрешений**. Пути в логах не
        печатались вовсе, поэтому распределение по субъектам и по границе каталога
        было невыводимо из прежних прогонов.

        `gated=False` при `requires_permission=True` и субъекте, отличном от
        `MODEL`, — это и есть P1-56 в одной строке: сегодня разрешение
        спрашивает только turn-путь.

        Замер обязан быть неломающим: горячий путь исполнения инструментов не
        должен падать из-за наблюдаемости.
        """
        try:
            definition = self._tools.get(acp_tool_name)
            requires_permission = definition.requires_permission if definition else None

            path = arguments.get("path") if isinstance(arguments, dict) else None
            cwd = getattr(getattr(session, "config", None), "cwd", None)
            inside_cwd: bool | None = None
            if isinstance(path, str) and path and cwd:
                # Тем же правилом, каким принимается решение: замер, меряющий
                # границу по-своему, отвечал бы не про ту границу.
                inside_cwd = is_inside_cwd(normalize_path(cwd, path), cwd)

            logger.info(
                "tool_invocation_probe",
                session_id=session_id_of(session),
                subject=subject.value,
                acp_tool_name=acp_tool_name,
                requires_permission=requires_permission,
                # Спрашивает разрешение сегодня только turn-путь: остальные
                # субъекты исполняют защищённый инструмент молча (P1-56).
                gated=bool(requires_permission) and subject is ToolInvocationSubject.MODEL,
                path=path if isinstance(path, str) else None,
                inside_cwd=inside_cwd,
                command_preview=_command_preview(arguments),
            )
        except Exception as error:  # noqa: BLE001 — замер не вправе ронять исполнение
            logger.debug("tool_invocation_probe_failed", error=str(error))

    @staticmethod
    def _path_boundary_violation(arguments: dict[str, Any], session: Any) -> str | None:
        """Причина отказа, если путь инвокации выходит за рабочий каталог.

        Условия те же, что были у обработчиков: правило действует, когда путь —
        непустая строка, а рабочий каталог сессии известен. Проверяется
        нормализованный путь, и текст отказа сохранён дословно — он уходит модели
        в теле `role: tool`, и его изменение сдвинуло бы LLM-payload.
        """
        if not isinstance(arguments, dict):
            return None
        path = arguments.get("path")
        if not isinstance(path, str) or not path.strip():
            return None
        cwd = getattr(getattr(session, "config", None), "cwd", None)
        if not cwd:
            return None

        normalized = normalize_path(cwd, path)
        if is_inside_cwd(normalized, cwd):
            return None
        return outside_cwd_error(normalized, cwd)

    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        session: Any = None,
        subject: ToolInvocationSubject = ToolInvocationSubject.UNKNOWN,
    ) -> ToolExecutionResult:
        """Выполнить инструмент асинхронно с поддержкой async executors.

        Поддерживает как синхронные, так и асинхронные executors.
        Metadata из ToolExecutionResult сохраняется в результате.

        Args:
            session_id: ID сессии для контекста выполнения
            tool_name: Имя инструмента (может быть в LLM формате с `_`)
            arguments: Аргументы для выполнения
            session: Опциональный доменный агрегат сессии для executors.
                Ядро держит read-проекцию (`SessionView`) и передаёт её сюда как
                есть — разворачиваем на границе (`writable_session`), потому что
                инструменты состояние меняют (реестр терминалов,
                `set_config_value`), а проекция read-only.

        Returns:
            ToolExecutionResult с успехом/ошибкой и metadata если доступен
        """
        session = writable_session(session)

        # Конвертируем LLM имя обратно в ACP формат для lookup в registry
        acp_tool_name = llm_name_to_acp_name(tool_name)

        logger.debug(
            "tool registry execute_tool called",
            session_id=session_id,
            tool_name=tool_name,
            acp_tool_name=acp_tool_name,
            arguments=arguments,
            has_session=session is not None,
        )

        self._probe_invocation(acp_tool_name, arguments, session, subject)

        # Точка применения (PEP, ADR-009 шаг 1). Сегодня она отклоняет ровно один
        # случай — инвокацию, не назвавшую субъект. Это нулевое изменение
        # поведения: замер 2026-08-10 дал 518 инвокаций и **ни одной** `unknown`,
        # то есть все шесть продакшн-вызывающих себя называют.
        #
        # Отклонение нужно не ради самой проверки, а ради того, чтобы «шов нельзя
        # обойти» перестало держаться на памяти автора нового вызова: без него
        # умолчание `UNKNOWN` тихо давало бы права, как их тихо давал
        # `terminal_counter` (P2-58).
        #
        # Политику для остальных субъектов шаг 1 намеренно не меняет: `context`
        # по-прежнему исполняет всё, что исполнял. Это шаг 2.
        if subject is ToolInvocationSubject.UNKNOWN:
            logger.warning(
                "tool_invocation_subject_missing",
                session_id=session_id_of(session),
                acp_tool_name=acp_tool_name,
            )
            return ToolExecutionResult(
                success=False,
                error=(
                    f"Инвокация инструмента '{acp_tool_name}' не назвала субъект: "
                    f"вызывающий обязан передать `subject` (ADR-009)."
                ),
            )

        # Граница рабочего каталога — правило политики, применяемое на шве
        # (ADR-009, шаг 2б). Раньше оно было написано руками в двух обработчиках
        # `fs/*`; теперь его получает всякая инвокация с путём, включая будущие
        # инструменты и всех вызывающих. Вне каталога — отказ обоим субъектам:
        # для `context` `Ask` невыразим, а для модели отказ и был поведением.
        boundary_error = self._path_boundary_violation(arguments, session)
        if boundary_error is not None:
            logger.info(
                "tool_invocation_outside_cwd",
                session_id=session_id_of(session),
                subject=subject.value,
                acp_tool_name=acp_tool_name,
            )
            return ToolExecutionResult(success=False, error=boundary_error)

        # Проверка существования инструмента (по ACP имени)
        if acp_tool_name not in self._tools:
            logger.error(
                "tool not found in registry",
                tool_name=tool_name,
                acp_tool_name=acp_tool_name,
                registered_tools=list(self._tools.keys()),
            )
            return ToolExecutionResult(
                success=False,
                error=f"Инструмент '{acp_tool_name}' не найден в реестре",
            )

        # Получение обработчика
        handler = self._handlers[acp_tool_name]
        is_async = inspect.iscoroutinefunction(handler)

        logger.debug(
            "tool handler found",
            tool_name=tool_name,
            acp_tool_name=acp_tool_name,
            is_async=is_async,
            handler_type=type(handler).__name__,
        )

        try:
            # Проверяем является ли обработчик асинхронным
            if is_async:
                logger.debug(
                    "executing async tool handler",
                    tool_name=tool_name,
                    acp_tool_name=acp_tool_name,
                )
                # Для async executors вызываем await
                # Если session доступен, передаём его в handler
                if session is not None and "session" in inspect.signature(handler).parameters:
                    result = await handler(session=session, **arguments)
                else:
                    result = await handler(**arguments)
            else:
                logger.debug(
                    "executing sync tool handler",
                    tool_name=tool_name,
                    acp_tool_name=acp_tool_name,
                )
                # Для синхронных функций вызываем напрямую
                output = handler(**arguments)
                result = ToolExecutionResult(
                    success=True,
                    output=str(output) if output is not None else None,
                )

            logger.info(
                "tool handler execution completed",
                tool_name=tool_name,
                acp_tool_name=acp_tool_name,
                success=result.success,
                has_output=bool(result.output),
                has_error=bool(result.error),
                has_metadata=bool(result.metadata),
            )

            # Возвращаем результат с сохранением metadata
            return result

        except Exception as exc:
            # Обработка исключений при выполнении
            logger.error(
                "tool handler execution failed with exception",
                tool_name=tool_name,
                acp_tool_name=acp_tool_name,
                error=str(exc),
                exc_info=True,
            )
            error_msg = f"Ошибка при выполнении инструмента '{acp_tool_name}': {str(exc)}"
            return ToolExecutionResult(
                success=False,
                error=error_msg,
            )
