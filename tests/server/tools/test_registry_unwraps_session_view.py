"""Инструменты получают носитель состояния, а не read-проекцию ядра.

Ядро агента (и Context Manager внутри него) читает сессию через порт `SessionView`
и передаёт этот же объект в `ToolRegistry.execute_tool` — так устроен контракт
порта. Инструменты состояние **меняют** (реестр терминалов, `set_config_value`),
поэтому проекция им не годится.

Регресс, который закрывают эти тесты, найден живым прогоном после флипа turn-пути
на доменный агрегат (ADR-006, фаза D шаг 3): в логе 54 подряд
`'DomainSessionView' object has no attribute 'config'` — падали и `fs/read_text_file`,
и `terminal/create`, то есть Context Manager не собирал контекст вообще. Тесты
этого не показывали: они зовут реестр напрямую и подают агрегат.
"""

from __future__ import annotations

from typing import Any

import pytest

from codelab.server.domain.value_objects import ToolInvocationSubject
from codelab.server.mapping.session_view import DomainSessionView
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.registry import SimpleToolRegistry
from tests.server._domain_sessions import make_domain_session


def _registry_capturing_session() -> tuple[SimpleToolRegistry, list[Any]]:
    """Реестр с одним инструментом, запоминающим полученную сессию."""
    registry = SimpleToolRegistry()
    seen: list[Any] = []

    async def handler(session: Any, **_: Any) -> ToolExecutionResult:
        seen.append(session)
        return ToolExecutionResult(success=True, output=session.config.cwd)

    registry.register_tool(
        name="fs/read_text_file",
        description="test",
        parameters={},
        kind="read",
        executor=handler,
    )
    return registry, seen


@pytest.mark.asyncio
async def test_view_is_unwrapped_to_the_aggregate() -> None:
    """Проекция разворачивается в агрегат — инструмент видит носитель."""
    registry, seen = _registry_capturing_session()
    session = make_domain_session(session_id="sess_1", cwd="/work")

    result = await registry.execute_tool(
        "sess_1",
        "fs/read_text_file",
        {"path": "A.md"},
        session=DomainSessionView(session),
        subject=ToolInvocationSubject.MODEL,
    )

    assert result.success
    assert result.output == "/work"
    assert seen == [session], "инструмент обязан получить сам агрегат, а не проекцию"


@pytest.mark.asyncio
async def test_aggregate_is_passed_through_unchanged() -> None:
    """Агрегат (turn-путь) доходит до инструмента как есть."""
    registry, seen = _registry_capturing_session()
    session = make_domain_session(session_id="sess_1", cwd="/work")

    await registry.execute_tool(
        "sess_1",
        "fs/read_text_file",
        {},
        session=session,
        subject=ToolInvocationSubject.MODEL,
    )

    assert seen == [session]


@pytest.mark.asyncio
async def test_mutation_through_the_view_reaches_the_session() -> None:
    """Мутация инструмента видна в сессии, хотя ядро передало read-проекцию.

    Именно ради этого разворачивание живёт в реестре: вернуть проекцию было бы
    «успешно ничего не изменил» — самый тихий класс дефектов.
    """
    registry = SimpleToolRegistry()

    async def handler(session: Any, **_: Any) -> ToolExecutionResult:
        session.set_config_value("project_structure", "{}")
        return ToolExecutionResult(success=True, output="ok")

    registry.register_tool(
        name="terminal/create",
        description="test",
        parameters={},
        kind="execute",
        executor=handler,
    )
    session = make_domain_session(session_id="sess_1", cwd="/work")

    await registry.execute_tool(
        "sess_1",
        "terminal/create",
        {},
        session=DomainSessionView(session),
        subject=ToolInvocationSubject.MODEL,
    )

    assert session.config.config_values["project_structure"] == "{}"
