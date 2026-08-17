"""Раскладка «снимок + JSONL» и дописывание журнала (шаг 6b ADR-008).

Гейты держат три свойства, ради которых шаг делался: журнал дописывается, а не
переписывается; снимок его не дублирует; однофайловые документы расщепляются
сами и не теряют записей.

Backend здесь только `JsonFileStorage`: на in-memory дописывания нет по смыслу, и
проверка «мутировали, но не сохранили» на нём слепа.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codelab.server.storage.document import SessionDocument
from codelab.server.storage.json_file import JsonFileStorage


def _record(text: str) -> dict:
    return {"event": "user_message_recorded", "data": {"blocks": [{"type": "text", "text": text}]}}


def _doc(session_id: str = "sess_j", **fields) -> SessionDocument:
    return SessionDocument(session_id=session_id, cwd="/work", mcp_servers=[], **fields)


def _journal_lines(tmp_path: Path, session_id: str = "sess_j") -> list[dict]:
    path = tmp_path / f"{session_id}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class TestLayout:
    @pytest.mark.asyncio
    async def test_snapshot_does_not_carry_the_journal(self, tmp_path: Path) -> None:
        """Снимок журнала не несёт — иначе это была бы вторая копия."""
        storage = JsonFileStorage(tmp_path)
        doc = _doc(events_history=[_record("раз"), _record("два")])

        await storage.save_session(doc)

        snapshot = json.loads((tmp_path / "sess_j.json").read_text(encoding="utf-8"))
        assert snapshot["events_history"] == []
        assert len(_journal_lines(tmp_path)) == 2

    @pytest.mark.asyncio
    async def test_load_composes_snapshot_and_journal(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_doc(events_history=[_record("раз")], title="T"))

        loaded = await JsonFileStorage(tmp_path).load_session("sess_j")

        assert loaded is not None
        assert loaded.title == "T"
        assert loaded.events_history == [_record("раз")]

    @pytest.mark.asyncio
    async def test_delete_removes_the_journal_too(self, tmp_path: Path) -> None:
        """Иначе журнал пережил бы удаление и достался новой сессии с тем же id."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_doc(events_history=[_record("раз")]))

        assert await storage.delete_session("sess_j") is True

        assert not (tmp_path / "sess_j.jsonl").exists()


class TestListReadsSnapshotsOnly:
    """`list_sessions` журнал не читает — ради этого в том числе выбрана раскладка."""

    @pytest.mark.asyncio
    async def test_journal_is_not_read(self, tmp_path: Path) -> None:
        """Гейт стоит на испорченном журнале: если бы список его читал, он бы упал.

        Проверка через порчу, а не через счётчик чтений: она держит свойство, а не
        реализацию, и переживёт замену бэкенда.
        """
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_doc(events_history=[_record("раз")], title="T"))
        (tmp_path / "sess_j.jsonl").write_text("{это не json\n", encoding="utf-8")

        page, _ = await JsonFileStorage(tmp_path).list_sessions()

        assert [s.title for s in page] == ["T"]

    @pytest.mark.asyncio
    async def test_listing_does_not_poison_the_journal_length_cache(self, tmp_path: Path) -> None:
        """После списка запись обязана дописать хвост, а не продублировать журнал.

        Список журнала не читает, поэтому записать в кэш «на диске 0» он не вправе:
        следующая запись сочла бы диск пустым и записала бы всё заново.
        """
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_doc(events_history=[_record("раз")]))

        fresh = JsonFileStorage(tmp_path)
        await fresh.list_sessions()
        doc = await fresh.load_session("sess_j")
        assert doc is not None
        doc.events_history.append(_record("два"))
        await fresh.save_session(doc)

        assert [r["data"]["blocks"][0]["text"] for r in _journal_lines(tmp_path)] == ["раз", "два"]


class TestAppendNotRewrite:
    @pytest.mark.asyncio
    async def test_existing_lines_are_not_rewritten(self, tmp_path: Path) -> None:
        """Уже записанная строка остаётся байт-в-байт — журнал append-only.

        Проверка идёт по байтам префикса, а не по разобранным записям: перезапись
        с той же семантикой, но другим форматированием, тоже была бы перезаписью
        и стоила бы ровно того, что шаг убирает.
        """
        storage = JsonFileStorage(tmp_path)
        doc = _doc(events_history=[_record("раз")])
        await storage.save_session(doc)
        first = (tmp_path / "sess_j.jsonl").read_bytes()

        doc.events_history.append(_record("два"))
        await storage.save_session(doc)

        after = (tmp_path / "sess_j.jsonl").read_bytes()
        assert after.startswith(first)
        assert len(_journal_lines(tmp_path)) == 2

    @pytest.mark.asyncio
    async def test_save_without_new_events_writes_nothing_to_the_journal(
        self, tmp_path: Path
    ) -> None:
        storage = JsonFileStorage(tmp_path)
        doc = _doc(events_history=[_record("раз")])
        await storage.save_session(doc)
        before = (tmp_path / "sess_j.jsonl").read_bytes()

        doc.title = "изменилось только это"
        await storage.save_session(doc)

        assert (tmp_path / "sess_j.jsonl").read_bytes() == before

    @pytest.mark.asyncio
    async def test_tail_is_computed_without_the_process_cache(self, tmp_path: Path) -> None:
        """Второй процесс дописывает хвост, а не дубли.

        Кэш длины журнала процессный; свежий экземпляр хранилища его не имеет и
        обязан посчитать записи по файлу. Без этого перезапуск сервера удваивал бы
        журнал на первой же записи.
        """
        first = JsonFileStorage(tmp_path)
        doc = _doc(events_history=[_record("раз")])
        await first.save_session(doc)

        second = JsonFileStorage(tmp_path)
        reloaded = await second.load_session("sess_j")
        assert reloaded is not None
        reloaded.events_history.append(_record("два"))
        await second.save_session(reloaded)

        assert [r["data"]["blocks"][0]["text"] for r in _journal_lines(tmp_path)] == ["раз", "два"]


class TestSplitOfSingleFileDocuments:
    @pytest.mark.asyncio
    async def test_first_write_moves_the_journal_out(self, tmp_path: Path) -> None:
        """Документ до 6b расщепляется первой же записью, без отдельной миграции.

        Тот же приём, что в 4f и 4g: признак несёт документ (журнала рядом нет), а
        не версия схемы.
        """
        legacy = _doc(events_history=[_record("раз"), _record("два")]).model_dump(mode="json")
        (tmp_path / "sess_j.json").write_text(
            json.dumps(legacy, ensure_ascii=False), encoding="utf-8"
        )
        storage = JsonFileStorage(tmp_path)

        loaded = await storage.load_session("sess_j")
        assert loaded is not None
        assert len(loaded.events_history) == 2
        assert not (tmp_path / "sess_j.jsonl").exists()

        await storage.save_session(loaded)

        assert len(_journal_lines(tmp_path)) == 2
        snapshot = json.loads((tmp_path / "sess_j.json").read_text(encoding="utf-8"))
        assert snapshot["events_history"] == []

    @pytest.mark.asyncio
    async def test_session_without_events_has_no_journal_file(self, tmp_path: Path) -> None:
        """Сессия без событий файла журнала не заводит — писать в него нечего.

        Читается она при этом как обычная: отсутствие журнала и пустой журнал
        дают одно и то же, потому что в снимке событий тоже нет. Различать их
        приходится только для документов до 6b, у которых журнал лежит **внутри**
        снимка, — этот случай проверяет тест выше.
        """
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_doc())

        assert not (tmp_path / "sess_j.jsonl").exists()

        doc = await storage.load_session("sess_j")
        assert doc is not None
        assert doc.events_history == []
