"""Область транзакции над сессией (ADR-007).

Инвариант владения: состояние принадлежит транзакции, а не процессу и не объекту.
Область даёт три свойства конструктивно, а не дисциплиной вызывающего: одна
загрузка, сериализация пересекающихся запросов, запись при успешном выходе и её
отсутствие при исключении.

Дефекты, из которых это выросло: P2-42 (две загрузки за запрос, ни одного
сохранения) и P0-39 (решения писались в копию, которую никто не видел).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from codelab.server.domain.session import Session, SessionConfig
from codelab.server.domain.value_objects import SessionId
from codelab.server.storage import JsonFileStorage, SessionRepository


def _repo(tmp_path: Path) -> SessionRepository:
    return SessionRepository(backend=JsonFileStorage(tmp_path))


async def _seed(repo: SessionRepository, session_id: str = "sess_x") -> None:
    await repo.save_session(
        Session(id=SessionId(session_id), config=SessionConfig(cwd="/start"))
    )


class TestCommitSemantics:
    @pytest.mark.asyncio
    async def test_commit_on_successful_exit(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        await _seed(repo)

        async with repo.transaction("sess_x") as session:
            assert session is not None
            session.set_title("Готово")

        on_disk = await _repo(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.title == "Готово"

    @pytest.mark.asyncio
    async def test_no_write_on_exception(self, tmp_path: Path) -> None:
        """Неудачная транзакция не оставляет полуправки."""
        repo = _repo(tmp_path)
        await _seed(repo)

        with pytest.raises(RuntimeError):
            async with repo.transaction("sess_x") as session:
                assert session is not None
                session.set_title("Не должно сохраниться")
                raise RuntimeError("boom")

        on_disk = await _repo(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.title is None

    @pytest.mark.asyncio
    async def test_missing_session_yields_none_and_writes_nothing(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)

        async with repo.transaction("missing") as session:
            assert session is None

        assert await _repo(tmp_path).load_session("missing") is None

    @pytest.mark.asyncio
    async def test_single_load_per_transaction(self, tmp_path: Path) -> None:
        """Вторая загрузка дала бы вторую копию — так был устроен P2-42."""
        backend = JsonFileStorage(tmp_path)
        repo = SessionRepository(backend=backend)
        await _seed(repo)

        loads = 0
        original = backend.load_session

        async def _counting(session_id: str):
            nonlocal loads
            loads += 1
            return await original(session_id)

        backend.load_session = _counting  # type: ignore[method-assign]

        async with repo.transaction("sess_x") as session:
            assert session is not None
            session.set_title("T")

        assert loads == 1


class TestConcurrentTransactionsDoNotLoseUpdates:
    """Пересекающиеся запросы по одной сессии — норма: turn разорван обменами с клиентом."""

    @pytest.mark.asyncio
    async def test_second_transaction_sees_first_commit(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        await _seed(repo)
        order: list[str] = []

        async def first() -> None:
            async with repo.transaction("sess_x") as session:
                assert session is not None
                order.append("first:in")
                await asyncio.sleep(0.05)  # пока держим область, приходит второй запрос
                session.set_title("first")
                order.append("first:out")

        async def second() -> None:
            await asyncio.sleep(0.01)
            async with repo.transaction("sess_x") as session:
                assert session is not None
                order.append("second:in")
                # Без блокировки здесь была бы копия, загруженная до коммита первого,
                # и запись второго затёрла бы заголовок первого
                assert session.title == "first"
                session.set_config_value("mode", "standard")
                order.append("second:out")

        await asyncio.gather(first(), second())

        assert order == ["first:in", "first:out", "second:in", "second:out"]
        on_disk = await _repo(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.title == "first"
        assert on_disk.get_config_value("mode") == "standard"

    @pytest.mark.asyncio
    async def test_different_sessions_are_not_serialized(self, tmp_path: Path) -> None:
        """Блокировка на сессию, а не на хранилище: чужая сессия не должна ждать."""
        repo = _repo(tmp_path)
        await _seed(repo, "a")
        await _seed(repo, "b")
        inside: set[str] = set()
        overlapped = False

        async def hold_a() -> None:
            nonlocal overlapped
            async with repo.transaction("a") as session:
                assert session is not None
                inside.add("a")
                await asyncio.sleep(0.05)
                # b успел войти в свою область, пока эта ещё открыта
                overlapped = "b" in inside
                session.set_title("a")

        async def hold_b() -> None:
            async with repo.transaction("b") as session:
                assert session is not None
                inside.add("b")
                session.set_title("b")

        await asyncio.gather(hold_a(), hold_b())

        # Проверяется одновременность, а не порядок входа: он зависит от того, кто
        # раньше уступит управление на загрузке
        assert overlapped, "транзакции по разным сессиям сериализовались"

    @pytest.mark.asyncio
    async def test_lock_released_after_exception(self, tmp_path: Path) -> None:
        """Сорвавшаяся транзакция не должна запирать сессию навсегда."""
        repo = _repo(tmp_path)
        await _seed(repo)

        with pytest.raises(RuntimeError):
            async with repo.transaction("sess_x"):
                raise RuntimeError("boom")

        async with repo.transaction("sess_x") as session:
            assert session is not None
            session.set_title("после сбоя")

        on_disk = await _repo(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.title == "после сбоя"
