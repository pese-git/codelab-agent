"""Замер авторизации инвокации — шаг 0 ADR-009.

Замер отвечает на вопрос, который нельзя снять задним числом: **что именно и от
чьего имени исполняется мимо гейта разрешений**. Пути в логах не печатались
вовсе (ноль вхождений `path=` за прогон 2026-08-10), поэтому распределение по
субъектам и по границе рабочего каталога было невыводимо из прежних прогонов.

Гейты здесь двух родов, и это разделение существенно:

* **субъект называют вызывающие** — иначе замер покажет `unknown`, и P1-56
  останется неизмеримым;
* **замер ничего не решает** — шаг 0 обязан быть нулевым по поведению, иначе
  живой прогон не отличит ошибку шва от смены политики.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import structlog

from codelab.server.domain.session import Session, SessionConfig
from codelab.server.domain.value_objects import SessionId, ToolInvocationSubject
from codelab.server.tools.base import ToolDefinition, ToolExecutionResult
from codelab.server.tools.registry import SimpleToolRegistry


def _session(cwd: str) -> Session:
    return Session(id=SessionId("s"), config=SessionConfig(cwd=cwd))


def _registry(*, requires_permission: bool = True) -> SimpleToolRegistry:
    registry = SimpleToolRegistry()

    async def handler(session: Any = None, **arguments: Any) -> ToolExecutionResult:
        return ToolExecutionResult(success=True, output="ok")

    registry.register(
        ToolDefinition(
            name="fs/read_text_file",
            description="read",
            parameters={},
            kind="read",
            requires_permission=requires_permission,
        ),
        handler,
    )
    return registry


@pytest.fixture
def probes() -> list[dict[str, Any]]:
    """Перехват записей structlog: замер проверяется по тому, что он пишет."""
    captured: list[dict[str, Any]] = []

    def processor(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        if event_dict.get("event") == "tool_invocation_probe":
            captured.append(dict(event_dict))
        return event_dict

    original = structlog.get_config()["processors"]
    structlog.configure(processors=[processor, *original])
    yield captured
    structlog.configure(processors=original)


class TestSubjectIsMeasured:
    @pytest.mark.asyncio
    async def test_context_subject_is_recorded_as_ungated(
        self, tmp_path: Path, probes: list[dict[str, Any]]
    ) -> None:
        """Защищённый инструмент от имени контекста — исполнение мимо гейта.

        Это P1-56 в одной строке замера: `requires_permission=True` и
        `gated=False`.
        """
        registry = _registry(requires_permission=True)
        target = tmp_path / "a.py"
        target.write_text("x")

        await registry.execute_tool(
            "s",
            "fs/read_text_file",
            {"path": str(target)},
            session=_session(str(tmp_path)),
            subject=ToolInvocationSubject.CONTEXT,
        )

        assert len(probes) == 1
        probe = probes[0]
        assert probe["subject"] == "context"
        assert probe["requires_permission"] is True
        assert probe["gated"] is False
        assert probe["inside_cwd"] is True

    @pytest.mark.asyncio
    async def test_model_subject_is_recorded_as_gated(
        self, tmp_path: Path, probes: list[dict[str, Any]]
    ) -> None:
        """Turn-путь — единственный, кто разрешение сегодня спрашивает."""
        registry = _registry(requires_permission=True)

        await registry.execute_tool(
            "s",
            "fs/read_text_file",
            {"path": str(tmp_path / "a.py")},
            session=_session(str(tmp_path)),
            subject=ToolInvocationSubject.MODEL,
        )

        assert probes[0]["gated"] is True

    @pytest.mark.asyncio
    async def test_unnamed_caller_is_visible_as_unknown(
        self, tmp_path: Path, probes: list[dict[str, Any]]
    ) -> None:
        """Путь, не назвавший субъект, обязан быть виден, а не молча сойти за модель.

        Умолчание `UNKNOWN` существует ради этого: иначе новый вызывающий снова
        окажется мимо гейта незаметно — тот же класс, что `terminal_counter`
        (P2-58).
        """
        registry = _registry()

        await registry.execute_tool(
            "s", "fs/read_text_file", {"path": "a.py"}, session=_session(str(tmp_path))
        )

        assert probes[0]["subject"] == "unknown"
        assert probes[0]["gated"] is False

    @pytest.mark.asyncio
    async def test_path_outside_cwd_is_visible(
        self, tmp_path: Path, probes: list[dict[str, Any]]
    ) -> None:
        """Граница каталога измеряется, а не предполагается.

        Первая редакция ADR-009 утверждала, что путь Context Manager может уйти
        за `cwd`; обработчик `fs/read_text_file` это уже отклоняет
        (`filesystem.py:180-187`). Замер обязан показывать саму величину, чтобы
        вывод о границе делался по числу, а не по памяти.
        """
        registry = _registry()

        await registry.execute_tool(
            "s",
            "fs/read_text_file",
            {"path": "/etc/passwd"},
            session=_session(str(tmp_path)),
            subject=ToolInvocationSubject.CONTEXT,
        )

        assert probes[0]["inside_cwd"] is False

    @pytest.mark.asyncio
    async def test_terminal_command_is_visible_separately(
        self, tmp_path: Path, probes: list[dict[str, Any]]
    ) -> None:
        """Команда терминала — случай, где граница пути неприменима.

        Тяжесть P1-56 сосредоточена здесь: `terminal/create` объявлен
        `requires_permission=True`, а Context Manager запускает команды, не
        спрашивая. Без превью команды в замере `find` не отличить от
        произвольной.
        """
        registry = SimpleToolRegistry()

        async def handler(session: Any, **arguments: Any) -> ToolExecutionResult:
            return ToolExecutionResult(success=True, output="ok")

        registry.register(
            ToolDefinition(
                name="terminal/create",
                description="create",
                parameters={},
                kind="execute",
                requires_permission=True,
            ),
            handler,
        )

        await registry.execute_tool(
            "s",
            "terminal/create",
            {"command": "find . -type f"},
            session=_session(str(tmp_path)),
            subject=ToolInvocationSubject.CONTEXT,
        )

        assert probes[0]["command_preview"] == "find . -type f"
        assert probes[0]["inside_cwd"] is None
        assert probes[0]["gated"] is False


class TestProbeChangesNothing:
    """Шаг 0 нулевой по поведению: замер не вправе ни решать, ни ронять."""

    @pytest.mark.asyncio
    async def test_execution_succeeds_for_every_subject(self, tmp_path: Path) -> None:
        registry = _registry(requires_permission=True)

        for subject in ToolInvocationSubject:
            if subject is ToolInvocationSubject.UNKNOWN:
                continue  # неназвавшийся отклоняется PEP — отдельный гейт ниже
            result = await registry.execute_tool(
                "s",
                "fs/read_text_file",
                {"path": "a.py"},
                session=_session(str(tmp_path)),
                subject=subject,
            )
            assert result.success is True, f"замер изменил поведение для {subject}"

    @pytest.mark.asyncio
    async def test_probe_survives_session_without_config(self, tmp_path: Path) -> None:
        """Сессии может не быть вовсе — горячий путь не должен падать из-за замера."""
        registry = _registry()

        result = await registry.execute_tool(
            "s", "fs/read_text_file", {"path": "a.py"}, subject=ToolInvocationSubject.CONTEXT
        )

        assert result.success is True


class TestRealCallersNameTheirSubject:
    """Гейт мест вызова, а не только шва (ADR-009, шаг 0).

    Проверен возвратом дефекта — и первая версия его **не поймала**: тесты замера
    проверяли реестр в изоляции, поэтому снятие `subject=CONTEXT` у
    `ContextGatherer` не роняло ни одного из 596 тестов. Это тот же класс, что
    `terminal_counter` (P2-58): гарантия держалась бы на том, что автор нового
    вызова не забудет.

    Здесь субъект проверяется у **настоящего** вызывающего: подменяется только
    реестр, а путь сбора контекста исполняется свой.
    """

    @pytest.mark.asyncio
    async def test_context_gatherer_names_itself(self, tmp_path: Path) -> None:
        from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
        from codelab.server.agent.context.gatherer import ACPContextGatherer
        from codelab.server.agent.context.models import TaskProfile, TaskType

        seen: list[ToolInvocationSubject] = []

        class _RecordingRegistry:
            async def execute_tool(
                self,
                session_id: str,
                tool_name: str,
                arguments: dict[str, Any],
                session: Any = None,
                subject: ToolInvocationSubject = ToolInvocationSubject.UNKNOWN,
            ) -> ToolExecutionResult:
                seen.append(subject)
                return ToolExecutionResult(success=True, output="print('x')")

            def get_available_tools(self, *args: Any, **kwargs: Any) -> list[Any]:
                return []

        (tmp_path / "a.py").write_text("print('x')")
        gatherer = ACPContextGatherer(
            tool_registry=_RecordingRegistry(),
            dependency_graph=RegexDependencyGraph(),
            session_id="s",
        )
        profile = TaskProfile(
            task_type=TaskType.FEATURE,
            search_terms=["a"],
            target_modules=[],
            investigation_depth=1,
            needs_tests=False,
        )

        await gatherer.gather(profile, _session(str(tmp_path)))

        assert seen, "путь сбора контекста не обратился к реестру — гейт бессмыслен"
        assert set(seen) == {ToolInvocationSubject.CONTEXT}, (
            f"Context Manager обязан называть себя, получено: {set(seen)}"
        )


class TestEnforcementPoint:
    """Точка применения (PEP) — ADR-009, шаг 1.

    Шаг обязан быть **нулевым по поведению**: единственное, что PEP сегодня
    отклоняет, — инвокация, не назвавшая субъект, а таких в поле нет (518
    инвокаций прогона 2026-08-10, ни одной `unknown`). Смысл отклонения не в
    самой проверке, а в том, что «шов нельзя обойти» перестаёт держаться на
    памяти автора нового вызова.
    """

    @pytest.mark.asyncio
    async def test_unnamed_subject_is_rejected(self, tmp_path: Path) -> None:
        registry = _registry()

        result = await registry.execute_tool(
            "s", "fs/read_text_file", {"path": "a.py"}, session=_session(str(tmp_path))
        )

        assert result.success is False
        assert "subject" in (result.error or "")

    @pytest.mark.asyncio
    async def test_named_subjects_still_execute(self, tmp_path: Path) -> None:
        """Политика для названных субъектов шагом 1 не меняется.

        `context` по-прежнему исполняет всё, что исполнял: сужение — это шаг 2, и
        смешивать его с переносом шва нельзя, иначе расхождение на живом прогоне
        объяснялось бы и тем, и другим.
        """
        registry = _registry(requires_permission=True)

        for subject in (
            ToolInvocationSubject.MODEL,
            ToolInvocationSubject.CONTEXT,
            ToolInvocationSubject.CLIENT,
            ToolInvocationSubject.SYSTEM,
        ):
            result = await registry.execute_tool(
                "s",
                "fs/read_text_file",
                {"path": "a.py"},
                session=_session(str(tmp_path)),
                subject=subject,
            )
            assert result.success is True, f"шаг 1 изменил поведение для {subject}"

    @pytest.mark.asyncio
    async def test_probe_sees_invocation_before_rejection(
        self, tmp_path: Path, probes: list[dict[str, Any]]
    ) -> None:
        """Замер идёт до применения: иначе отклонённое стало бы невидимым.

        Порядок значим — по той же причине, по которой признак «в полёте»
        снимается до смены статуса (P2-63).
        """
        registry = _registry()

        await registry.execute_tool(
            "s", "fs/read_text_file", {"path": "a.py"}, session=_session(str(tmp_path))
        )

        assert probes[0]["subject"] == "unknown"
