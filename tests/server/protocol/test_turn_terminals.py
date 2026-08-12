"""Освобождение остатка терминалов turn'а (ADR-008, шаг 5.3, часть 2).

Обязанность освобождать лежит на **агенте** (`10-Terminal.md:109-111`), а фактический
приобретатель ресурса от лица модели — turn. Замер шести живых прогонов: turn-путь
создавал терминалы и освобождал 0 в пяти из них.

Ключевое свойство, которое здесь и проверяется: освобождается только **дожданный**
остаток. Освобождение терминала с незавершённым ожиданием убивает идущую команду
(`17-Schema.md:1060-1062`), и это окно наблюдалось живьём — отмена через 1.5 с после
`create` (`term_96847_1`, 2026-08-10).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

from codelab.server.client_rpc import ClientRPCCancelledError
from codelab.server.client_rpc.service import ClientRPCService
from codelab.server.protocol.turn_terminals import TurnTerminalReleaser
from codelab.server.rpc_holder import ClientRPCServiceHolder
from codelab.server.tools.executors.terminal_alias_registry import TerminalAliasRegistry
from tests.server._domain_sessions import make_domain_session


@pytest.fixture
def session():
    return make_domain_session(session_id="sess_release", cwd="/tmp", mcp_servers=[])


@pytest.fixture
def registry() -> TerminalAliasRegistry:
    return TerminalAliasRegistry(epoch="7")


def _make_releaser(
    registry: TerminalAliasRegistry,
    *,
    release_result: bool = True,
) -> tuple[TurnTerminalReleaser, MagicMock]:
    service = MagicMock(spec=ClientRPCService)
    service.release_terminal = AsyncMock(return_value=release_result)
    holder = ClientRPCServiceHolder()
    holder.service = service
    return TurnTerminalReleaser(aliases=registry, client_rpc_service_holder=holder), service


class TestWaitedRemainderIsReleased:
    async def test_waited_terminal_is_released(self, registry, session) -> None:
        alias = registry.register(session, "client-1")
        registry.mark_waited(session, alias)
        releaser, service = _make_releaser(registry)

        released = await releaser.release_turn_remainder(session, cause="completed")

        assert released == 1
        service.release_terminal.assert_awaited_once()
        assert registry.known_aliases(session) == []

    async def test_alias_is_dropped_only_on_successful_release(self, registry, session) -> None:
        """Неудачный RPC alias не снимает: иначе модель получила бы «неизвестный
        терминал» вместо правдивой ошибки, а терминал остался бы у клиента."""
        alias = registry.register(session, "client-1")
        registry.mark_waited(session, alias)
        releaser, _ = _make_releaser(registry, release_result=False)

        released = await releaser.release_turn_remainder(session, cause="completed")

        assert released == 0
        assert registry.known_aliases(session) == [alias]

    async def test_empty_remainder_costs_no_rpc(self, registry, session) -> None:
        releaser, service = _make_releaser(registry)

        assert await releaser.release_turn_remainder(session, cause="completed") == 0
        service.release_terminal.assert_not_awaited()

    async def test_empty_remainder_is_still_observable(self, registry, session) -> None:
        """Молчание шва неотличимо от «шов не достигнут» — и это уже стоило приёмки.

        Прогон 2026-08-12 (`sess_f5f9b789397b`) закончился штатно с `live=0`: модель
        освободила все три терминала сама. Записи не было, и по логу нельзя было
        сказать, исполнился ли шов вообще. То же слепое пятно, которое шаг 5.1 убрал у
        признака `waited`.
        """
        releaser, _ = _make_releaser(registry)

        with structlog.testing.capture_logs() as logs:
            await releaser.release_turn_remainder(session, cause="completed")

        records = [entry for entry in logs if entry["event"] == "turn_terminals_released"]
        assert len(records) == 1
        assert records[0]["released"] == 0
        assert records[0]["cause"] == "completed"

    async def test_release_is_idempotent_across_two_turn_ends(self, registry, session) -> None:
        alias = registry.register(session, "client-1")
        registry.mark_waited(session, alias)
        releaser, service = _make_releaser(registry)

        await releaser.release_turn_remainder(session, cause="completed")
        await releaser.release_turn_remainder(session, cause="completed")

        assert service.release_terminal.await_count == 1


class TestUnwaitedTerminalSurvives:
    async def test_unwaited_terminal_is_not_released(self, registry, session) -> None:
        """Единственное окно, где освобождение убивает идущую команду.

        Возврат дефекта (освобождать весь живой остаток) валит именно этот тест.
        """
        alias = registry.register(session, "client-1")
        releaser, service = _make_releaser(registry)

        released = await releaser.release_turn_remainder(session, cause="cancelled")

        assert released == 0
        service.release_terminal.assert_not_awaited()
        assert registry.unwaited_aliases(session) == [alias]

    async def test_mixed_remainder_releases_only_waited(self, registry, session) -> None:
        waited = registry.register(session, "client-waited")
        unwaited = registry.register(session, "client-unwaited")
        registry.mark_waited(session, waited)
        releaser, service = _make_releaser(registry)

        released = await releaser.release_turn_remainder(session, cause="cancelled")

        assert released == 1
        assert service.release_terminal.await_count == 1
        assert registry.known_aliases(session) == [unwaited]


class TestHotPathNeverFails:
    async def test_rpc_error_does_not_break_turn_end(self, registry, session) -> None:
        """Ответ на `session/prompt` уже построен: исключение здесь стоило бы turn'а."""
        first = registry.register(session, "client-1")
        second = registry.register(session, "client-2")
        registry.mark_waited(session, first)
        registry.mark_waited(session, second)
        releaser, service = _make_releaser(registry)
        service.release_terminal = AsyncMock(side_effect=[RuntimeError("boom"), True])

        released = await releaser.release_turn_remainder(session, cause="completed")

        assert released == 1
        assert registry.known_aliases(session) == [first]

    async def test_cancelled_rpc_stops_the_drain(self, registry, session) -> None:
        """Отмена приходит по всей сессии — остаток доживёт до следующего завершения."""
        first = registry.register(session, "client-1")
        second = registry.register(session, "client-2")
        registry.mark_waited(session, first)
        registry.mark_waited(session, second)
        releaser, service = _make_releaser(registry)
        service.release_terminal = AsyncMock(side_effect=ClientRPCCancelledError("cancelled"))

        released = await releaser.release_turn_remainder(session, cause="cancelled")

        assert released == 0
        assert registry.known_aliases(session) == [first, second]

    async def test_no_client_rpc_service_is_not_an_error(self, registry, session) -> None:
        alias = registry.register(session, "client-1")
        registry.mark_waited(session, alias)
        releaser = TurnTerminalReleaser(
            aliases=registry,
            client_rpc_service_holder=ClientRPCServiceHolder(),
        )

        assert await releaser.release_turn_remainder(session, cause="completed") == 0


class TestOnlyTurnEndPathsDrain:
    """Дренаж вызывается только из путей, исполняющихся в фоновой задаче.

    Ограничение сильнее, чем «turn кончился по воле модели», и его задал транспорт, а
    не вкус: stdio отправляет в фоновую задачу **только** `session/prompt`
    (`stdio.py:211`), поэтому agent→client RPC из любого другого обработчика
    взаимоблокируется — прочитать ответ может лишь тот receive-цикл, который этим
    ожиданием заблокирован. Измерено живьём 2026-08-12 (`sess_937ff13e9d1b`): дренаж на
    отмене повис, `session_cancel_handled` — последняя строка лога.

    Отсюда два разрешённых шва: штатное завершение (фоновая задача завершения или
    `BackgroundExecutor`) и ошибка пайплайна (внутри фоновой задачи `session/prompt`).
    Остаток отменённого turn'а сцеживается на следующем завершении — дренаж
    идемпотентен и накопителен. Гейт того же рода, что `test_seam_cannot_be_bypassed`
    у снятия turn'а (шаг 5.2): без него inline-путь вернулся бы молча.
    """

    _ALLOWED = {
        "protocol/turn_terminals.py",
        "protocol/background_executor.py",
        "protocol/handlers/prompt_orchestrator.py",
    }

    def test_drain_is_called_only_from_background_task_seams(self) -> None:
        server_root = Path(__file__).resolve().parents[3] / "src" / "codelab" / "server"
        callers = {
            str(path.relative_to(server_root))
            for path in server_root.rglob("*.py")
            if "release_turn_remainder(" in path.read_text(encoding="utf-8")
        }

        assert callers == self._ALLOWED
