"""Проекция реестра вызовов из журнала сессии (шаг 4g ADR-008).

Парная `history_projection`: журнал — источник, `tool_calls` — вид. Проекцию
можно выбросить и пересчитать, поэтому здесь нет ни состояния, ни носителя.

Проекция стала возможной только после того, как `ToolCallStarted` начал нести
имя инструмента, аргументы и идентификатор вызова у модели: связки внутреннего
`call_NNN` с этим идентификатором не нёс до 4g **ни один** вид записи, а
соединение по порядку внутри turn'а — догадка, а не тождество.

Два поля документа проекция не восстанавливает, и это не потеря: `locations` и
`raw_output` в сохранённом вызове пусты структурно. `ToolCallRegistry.create`
не принимает `raw_output`, `update_status` лишь копирует прежний результат, а
`Session.update_tool_call` не имеет ни одного продакшн-вызывающего. То
`raw_output`, что производят `terminal_executor` и MCP, живёт в
`ToolExecutionResult` и в нотификации клиенту и до `ToolCall` не доходит.
"""

from __future__ import annotations

from collections.abc import Iterable

from .journal import JournalEntry, ToolCallStarted, ToolCallStatusChanged
from .tool_call import ToolCall, ToolResult
from .value_objects import ToolCallStatus

__all__ = ["project_tool_calls"]


def project_tool_calls(entries: Iterable[JournalEntry]) -> dict[str, ToolCall]:
    """Собрать реестр вызовов из журнала.

    Порядок вставки — порядок появления вызовов: им ключуется и обход
    `get_all`, и порядок записи в документ.

    Статус берётся из журнала дословно, без матрицы переходов: журнал
    описывает то, что произошло, а матрица решает, что произойти **может**.
    Прогон матрицы по восстановлению отверг бы запись, которую сам же
    когда-то и породил.

    Args:
        entries: Записи журнала в исходном порядке.

    Returns:
        Вызовы по внутреннему идентификатору, в порядке появления.
    """
    calls: dict[str, ToolCall] = {}

    for entry in entries:
        match entry.event:
            case ToolCallStarted(
                tool_call_id=tool_call_id,
                title=title,
                kind=kind,
                status=status,
                content=content,
                tool_name=tool_name,
                arguments=arguments,
                tool_call_id_from_llm=tool_call_id_from_llm,
            ):
                calls[tool_call_id] = ToolCall(
                    id=tool_call_id,
                    # Fallback на `title` повторяет `ToolCallMapper.to_domain`:
                    # у вызовов client-RPC имени инструмента нет вовсе.
                    tool_name=tool_name if tool_name is not None else title,
                    arguments=dict(arguments) if arguments else {},
                    status=_status_of(status),
                    result=_result_of(content),
                    kind=kind,
                    title=title,
                    tool_call_id_from_llm=tool_call_id_from_llm,
                )
            case ToolCallStatusChanged(tool_call_id=tool_call_id, status=status, content=content):
                call = calls.get(tool_call_id)
                if call is None:
                    # Статус вызова, чьё создание в журнал не попало, восстановить
                    # не из чего: пропуск честнее вызова-призрака без имени.
                    continue
                call.status = _status_of(status)
                if content is not None:
                    call.result = _result_of(content)

    return calls


def _status_of(raw: str) -> ToolCallStatus:
    """Статус из записи; неизвестное значение — `pending`, как при разборе документа."""
    try:
        return ToolCallStatus(raw)
    except ValueError:
        return ToolCallStatus.PENDING


def _result_of(content: list[dict[str, object]] | None) -> ToolResult | None:
    """Результат вызова; без контента результата нет.

    `locations` и `raw_output` остаются пустыми — в документе они пусты
    структурно (см. модуль).
    """
    if not content:
        return None
    return ToolResult(content=[dict(item) for item in content])
