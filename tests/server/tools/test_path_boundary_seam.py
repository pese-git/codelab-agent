"""Граница рабочего каталога применяется на шве, а не у обработчика (ADR-009, шаг 2б).

Гейт возвратом дефекта: снять проверку в `SimpleToolRegistry.execute_tool` — и
падают все тесты этого файла, включая `test_context_cannot_read_outside_cwd`,
который ADR требует отдельной строкой.

Существенное здесь — **кто** её применяет. Прежде правило было написано руками в
двух обработчиках `fs/*`: инструмент, чей автор о нём не вспомнил бы, границы не
получал (тот же класс, что `terminal_counter` в P2-58). На шве её получает всякая
инвокация с путём, включая вызывающих, которые о границе не знают.
"""

from __future__ import annotations

from typing import Any

from codelab.server.domain.path_boundary import outside_cwd_error
from codelab.server.domain.value_objects import ToolInvocationSubject
from codelab.server.tools.base import ToolDefinition, ToolExecutionResult
from codelab.server.tools.registry import SimpleToolRegistry
from tests.server._domain_sessions import make_domain_session


def _make_session(cwd: str = "/work"):
    """Настоящий доменный агрегат: mock подменил бы и `cwd`, и результат правила."""
    return make_domain_session(session_id="sess_test", cwd=cwd)


def _registry() -> tuple[SimpleToolRegistry, list[dict[str, Any]]]:
    """Реестр с инструментом, который записывает дошедшие до него аргументы."""
    seen: list[dict[str, Any]] = []
    registry = SimpleToolRegistry()

    async def handler(session: Any = None, **arguments: Any) -> ToolExecutionResult:
        seen.append(arguments)
        return ToolExecutionResult(success=True, output="ok")

    registry.register(
        ToolDefinition(
            name="fs/read_text_file",
            description="test",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            kind="read",
        ),
        handler,
    )
    return registry, seen


class TestBoundaryHoldsForEverySubject:
    """Вне каталога — отказ, кем бы ни была названа инвокация."""

    async def test_model_cannot_read_outside_cwd(self) -> None:
        registry, seen = _registry()

        result = await registry.execute_tool(
            "sess_test",
            "fs/read_text_file",
            {"path": "/etc/passwd"},
            session=_make_session(),
            subject=ToolInvocationSubject.MODEL,
        )

        assert not result.success
        assert seen == [], "инвокация не должна доходить до обработчика"

    async def test_context_cannot_read_outside_cwd(self) -> None:
        """`Ask` для `context` невыразим, поэтому выход за каталог — отказ."""
        registry, seen = _registry()

        result = await registry.execute_tool(
            "sess_test",
            "fs/read_text_file",
            {"path": "../../secrets.txt"},
            session=_make_session(),
            subject=ToolInvocationSubject.CONTEXT,
        )

        assert not result.success
        assert seen == []

    async def test_error_text_is_preserved(self) -> None:
        """Текст отказа дословный: он уходит модели в теле `role: tool`."""
        registry, _ = _registry()

        result = await registry.execute_tool(
            "sess_test",
            "fs/read_text_file",
            {"path": "/etc/passwd"},
            session=_make_session(),
            subject=ToolInvocationSubject.MODEL,
        )

        assert result.error == outside_cwd_error("/etc/passwd", "/work")

    async def test_relative_path_is_normalized_before_the_check(self) -> None:
        """Проверяется нормализованный путь — иначе граница обходится `..`."""
        registry, seen = _registry()

        result = await registry.execute_tool(
            "sess_test",
            "fs/read_text_file",
            {"path": "sub/../../outside.txt"},
            session=_make_session(),
            subject=ToolInvocationSubject.MODEL,
        )

        assert not result.success
        assert seen == []


class TestBoundaryDoesNotOverreach:
    """Условия применения те же, что были у обработчиков."""

    async def test_path_inside_cwd_passes(self) -> None:
        registry, seen = _registry()

        result = await registry.execute_tool(
            "sess_test",
            "fs/read_text_file",
            {"path": "lib/main.dart"},
            session=_make_session(),
            subject=ToolInvocationSubject.CONTEXT,
        )

        assert result.success
        assert seen == [{"path": "lib/main.dart"}]

    async def test_invocation_without_path_is_untouched(self) -> None:
        """Инвокация без пути правилу не подлежит: у команды границы нет."""
        registry, seen = _registry()

        result = await registry.execute_tool(
            "sess_test",
            "fs/read_text_file",
            {"command": "find . -type f"},
            session=_make_session(),
            subject=ToolInvocationSubject.CONTEXT,
        )

        assert result.success
        assert seen == [{"command": "find . -type f"}]

    async def test_without_cwd_rule_does_not_apply(self) -> None:
        """Без известного рабочего каталога границу не с чем сравнивать.

        Условие сохранено от обработчиков дословно: там проверка тоже стояла под
        `if session.config.cwd`.
        """
        registry, seen = _registry()

        result = await registry.execute_tool(
            "sess_test",
            "fs/read_text_file",
            {"path": "/etc/passwd"},
            session=_make_session(cwd=""),
            subject=ToolInvocationSubject.MODEL,
        )

        assert result.success
        assert seen == [{"path": "/etc/passwd"}]


class TestHandlerNoLongerOwnsTheRule:
    """Владелец правила один — иначе оно снова разойдётся в копиях."""

    def test_filesystem_definitions_do_not_validate(self) -> None:
        """В обработчиках `fs/*` не осталось собственной проверки границы."""
        from pathlib import Path

        source = Path("src/codelab/server/tools/definitions/filesystem.py").read_text()

        assert "outside working directory" not in source
        assert "is_inside_cwd" not in source
