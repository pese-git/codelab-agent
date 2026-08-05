"""Compare-and-set по ревизии документа (ADR-007).

Копия сессии живёт через `await` — фоновое исполнение turn'а держит её, пока другие
запросы приходят и сохраняют свои решения. До ревизии такая копия молча затирала
всё, что записали тем временем; именно этот класс дважды стоил нам потерянных
решений (P0-39, P2-42).

Отклонение вместо перезаписи выбрано осознанно: конфликт должен быть видимым.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from codelab.server.exceptions import SessionRevisionConflictError
from codelab.server.storage import InMemoryStorage, JsonFileStorage, SessionStorage
from codelab.server.storage.document import SessionDocument


def _session(cwd: str = "/start") -> SessionDocument:
    return SessionDocument(session_id="sess_x", cwd=cwd, mcp_servers=[])


@pytest.fixture(params=["json", "memory"])
def storage_factory(request, tmp_path: Path):
    """Оба бэкенда: поведение не должно расходиться, иначе тесты на памяти пропустят конфликт."""
    if request.param == "json":
        return lambda: JsonFileStorage(tmp_path)
    shared = InMemoryStorage()
    return lambda: shared


class TestRevisionAdvances:
    @pytest.mark.asyncio
    async def test_revision_starts_at_zero_and_grows_per_write(self, storage_factory) -> None:
        storage: SessionStorage = storage_factory()
        session = _session()
        assert session.revision == 0

        await storage.save_session(session)
        assert session.revision == 1, "хранилище обязано вернуть новую ревизию в объект"

        loaded = await storage.load_session("sess_x")
        assert loaded is not None
        assert loaded.revision == 1

        loaded.cwd = "/next"
        await storage.save_session(loaded)
        assert loaded.revision == 2

    @pytest.mark.asyncio
    async def test_old_sessions_without_revision_start_at_zero(self, tmp_path: Path) -> None:
        """Формат меняется с миграцией: файл без поля читается, а не падает."""
        import json

        (tmp_path / "sess_old.json").write_text(
            json.dumps(
                {
                    "schema_version": 6,
                    "session_id": "sess_old",
                    "cwd": "/old",
                    "mcp_servers": [],
                }
            ),
            encoding="utf-8",
        )

        loaded = await JsonFileStorage(tmp_path).load_session("sess_old")

        assert loaded is not None
        assert loaded.revision == 0
        assert loaded.schema_version == 10


class TestStaleCopyIsRejected:
    """Ядро правки: копия, устаревшая к моменту записи, не должна затирать документ.

    Проверяется на файловом бэкенде: только он отдаёт копии. `InMemoryStorage`
    возвращает сам хранимый объект, поэтому устаревших копий там не возникает —
    для него случай проверяется отдельно, явно собранным объектом.
    """

    @pytest.mark.asyncio
    async def test_stale_copy_raises_conflict(self, tmp_path: Path) -> None:
        storage: SessionStorage = JsonFileStorage(tmp_path)
        await storage.save_session(_session("/start"))

        # Долгоживущая копия (так держит её фоновое исполнение turn'а)
        stale = await storage.load_session("sess_x")
        assert stale is not None

        # Тем временем другой запрос сохранил свои решения
        fresh = await storage.load_session("sess_x")
        assert fresh is not None
        fresh.set_title("решение другого запроса")
        await storage.save_session(fresh)

        stale.cwd = "/from_stale"
        with pytest.raises(SessionRevisionConflictError) as exc:
            await storage.save_session(stale)

        assert exc.value.session_id == "sess_x"
        assert exc.value.expected < exc.value.actual

    @pytest.mark.asyncio
    async def test_rejected_write_does_not_touch_document(self, tmp_path: Path) -> None:
        storage: SessionStorage = JsonFileStorage(tmp_path)
        await storage.save_session(_session("/start"))
        stale = await storage.load_session("sess_x")
        assert stale is not None
        fresh = await storage.load_session("sess_x")
        assert fresh is not None
        fresh.set_title("сохранено")
        await storage.save_session(fresh)

        stale.cwd = "/from_stale"
        with pytest.raises(SessionRevisionConflictError):
            await storage.save_session(stale)

        on_disk = await storage.load_session("sess_x")
        assert on_disk is not None
        assert on_disk.title == "сохранено", "решение другого запроса должно остаться"
        assert on_disk.cwd == "/start", "устаревшая запись не должна применяться"

    @pytest.mark.asyncio
    async def test_conflict_is_distinguishable_from_io_error(self, tmp_path: Path) -> None:
        """Конфликт не заворачивается в общий StorageError: вызывающий их различает."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session())
        stale = await storage.load_session("sess_x")
        assert stale is not None
        fresh = await storage.load_session("sess_x")
        assert fresh is not None
        await storage.save_session(fresh)

        with pytest.raises(SessionRevisionConflictError):
            await storage.save_session(stale)


class TestMemoryBackendKeepsSameGuard:
    """У памяти нет копий, но сверка обязана работать на отдельно собранном объекте.

    Иначе тесты, подменяющие хранилище памятью, пропустили бы конфликт как класс.
    """

    @pytest.mark.asyncio
    async def test_separately_built_object_with_stale_revision_is_rejected(self) -> None:
        storage = InMemoryStorage()
        await storage.save_session(_session("/start"))

        # Объект, собранный отдельно (revision=0), тогда как в хранилище уже 1
        stale = _session("/from_stale")

        with pytest.raises(SessionRevisionConflictError):
            await storage.save_session(stale)


class TestFirstWriteAndDamagedDocument:
    @pytest.mark.asyncio
    async def test_first_write_of_new_session_is_allowed(self, tmp_path: Path) -> None:
        """Документа ещё нет — сверять нечего."""
        storage = JsonFileStorage(tmp_path)

        await storage.save_session(_session())

        loaded = await storage.load_session("sess_x")
        assert loaded is not None
        assert loaded.revision == 1

    @pytest.mark.asyncio
    async def test_damaged_document_does_not_lock_session_forever(self, tmp_path: Path) -> None:
        """Битый файл не должен превращать CAS в невозможность записи."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session())
        (tmp_path / "sess_x.json").write_text("{ это не json", encoding="utf-8")

        await storage.save_session(_session("/recovered"))

        loaded = await storage.load_session("sess_x")
        assert loaded is not None
        assert loaded.cwd == "/recovered"


class TestDeletedSessionIsNotResurrected:
    """Удаление во время turn'а: запись устаревшей копии не должна вернуть сессию.

    Поведение было и до ревизии — запись просто пересоздавала файл. Теперь
    отсутствие документа при `revision > 0` трактуется как удаление и отклоняется:
    удаление было осознанным решением.
    """

    @pytest.mark.asyncio
    async def test_write_after_delete_is_rejected(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session())
        held = await storage.load_session("sess_x")
        assert held is not None
        await storage.delete_session("sess_x")

        with pytest.raises(SessionRevisionConflictError) as exc:
            await storage.save_session(held)

        assert exc.value.actual == 0, "0 означает «документа нет»"
        assert await storage.load_session("sess_x") is None

    @pytest.mark.asyncio
    async def test_first_write_of_fresh_object_still_allowed(self, tmp_path: Path) -> None:
        """Новая сессия (revision=0) записывается: документа нет и не должно быть."""
        storage = JsonFileStorage(tmp_path)

        await storage.save_session(_session())

        assert await storage.load_session("sess_x") is not None

    @pytest.mark.asyncio
    async def test_memory_backend_rejects_write_after_delete(self) -> None:
        storage = InMemoryStorage()
        await storage.save_session(_session())
        held = await storage.load_session("sess_x")
        assert held is not None
        await storage.delete_session("sess_x")

        with pytest.raises(SessionRevisionConflictError):
            await storage.save_session(held)


class TestOptimisticLimits:
    """Предел сверки зафиксирован явно, чтобы его не приняли за гарантию."""

    @pytest.mark.asyncio
    async def test_simultaneous_writers_are_not_detected(self, tmp_path: Path) -> None:
        """Проверка читается до записи, поэтому ровно одновременные писатели проходят.

        Это не дефект реализации, а свойство оптимистичной сверки без блокировки на
        файл: она ловит устаревшую копию (наблюдавшийся класс), но не точную гонку.
        Внутри процесса гонку закрывает блокировка в `repository.transaction()`, для
        нескольких воркеров понадобится CAS на уровне хранилища (ADR-007).
        """
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session())
        a = await storage.load_session("sess_x")
        b = await storage.load_session("sess_x")
        assert a is not None and b is not None

        a.cwd = "/from_a"
        b.cwd = "/from_b"
        await asyncio.gather(storage.save_session(a), storage.save_session(b))

        on_disk = await storage.load_session("sess_x")
        assert on_disk is not None
        # Побеждает последний писатель, конфликт не обнаружен — предел зафиксирован
        assert on_disk.cwd in {"/from_a", "/from_b"}

    @pytest.mark.asyncio
    async def test_transaction_serializes_and_avoids_conflict(self, tmp_path: Path) -> None:
        """Через область транзакции те же два писателя конфликта не дают."""
        from codelab.server.storage import SessionRepository

        repo = SessionRepository(backend=JsonFileStorage(tmp_path))
        await JsonFileStorage(tmp_path).save_session(_session())

        async def bump(title: str) -> None:
            async with repo.transaction("sess_x") as session:
                assert session is not None
                await asyncio.sleep(0)
                session.set_title(title)

        await asyncio.gather(bump("first"), bump("second"))

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.revision == 3, "три записи: создание и две транзакции"
