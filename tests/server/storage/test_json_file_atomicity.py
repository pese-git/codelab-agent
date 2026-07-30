"""Запись сессии атомарна (ADR-007).

Прямая запись в целевой файл оставляла обрезанный документ при падении посреди
записи или при двух писателях, а сессия уже занимает сотни килобайт (замер:
751 КБ на 53 вызова). Читатель обязан видеть либо прежний документ целиком, либо
новый целиком.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from codelab.server.exceptions import StorageError
from codelab.server.protocol.state import SessionState
from codelab.server.storage import JsonFileStorage


def _session(cwd: str = "/first") -> SessionState:
    return SessionState(session_id="sess_x", cwd=cwd, mcp_servers=[])


class TestSaveIsAtomic:
    @pytest.mark.asyncio
    async def test_failed_write_leaves_previous_document_intact(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session("/first"))

        # Падение после записи временного файла, до подмены целевого
        with patch("codelab.server.storage.json_file.os.replace", side_effect=OSError("boom")):
            with pytest.raises(StorageError):
                await storage.save_session(_session("/second"))

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.cwd == "/first", "прежний документ должен остаться целым"

    @pytest.mark.asyncio
    async def test_failed_write_leaves_no_temp_files(self, tmp_path: Path) -> None:
        """Мусор от неудачной записи не остаётся: иначе каталог сессий засорится."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session())

        with patch("codelab.server.storage.json_file.os.replace", side_effect=OSError("boom")):
            with pytest.raises(StorageError):
                await storage.save_session(_session("/second"))

        assert list(tmp_path.glob("*.tmp")) == []

    @pytest.mark.asyncio
    async def test_successful_write_replaces_document(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session("/first"))

        # Реальный поток: загрузить, изменить, записать — иначе CAS отклонит запись
        # копии с устаревшей ревизией (ADR-007)
        loaded = await storage.load_session("sess_x")
        assert loaded is not None
        loaded.cwd = "/second"
        await storage.save_session(loaded)

        raw = json.loads((tmp_path / "sess_x.json").read_text(encoding="utf-8"))
        assert raw["cwd"] == "/second"
        assert list(tmp_path.glob("*.tmp")) == []

    @pytest.mark.asyncio
    async def test_document_is_never_partially_visible(self, tmp_path: Path) -> None:
        """Пока идёт запись, читатель видит прежний документ, а не полуфабрикат."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session("/first"))
        seen: list[str] = []

        real_replace = os.replace

        def _peek_then_replace(src, dst):
            # В момент между записью tmp и подменой целевого файла
            snapshot = json.loads(Path(dst).read_text(encoding="utf-8"))
            seen.append(snapshot["cwd"])
            real_replace(src, dst)

        current = await storage.load_session("sess_x")
        assert current is not None
        current.cwd = "/second"
        with patch("codelab.server.storage.json_file.os.replace", _peek_then_replace):
            await storage.save_session(current)

        assert seen == ["/first"]
        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.cwd == "/second"


class TestConcurrentSaves:
    """Одновременные записи одной сессии не должны мешать друг другу.

    Первая версия правки давала временному файлу имя по PID — два параллельных
    сохранения делили один tmp, первый `os.replace` забирал его, второй падал с
    ENOENT. Поймано полным прогоном (e2e-тест отмены), не ревью.
    """

    @pytest.mark.asyncio
    async def test_parallel_saves_of_same_session_all_succeed(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        sessions = [_session(f"/p{i}") for i in range(8)]

        # Все копии с одной ревизией: проверка читается до записи, поэтому
        # одновременные писатели проходят CAS — предел оптимистичной сверки
        # зафиксирован тестом ниже (TestOptimisticLimits)
        await asyncio.gather(*(storage.save_session(s) for s in sessions))

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        # Побеждает последний писатель — семантика прежняя; важно, что никто не упал
        assert on_disk.cwd.startswith("/p")
        assert list(tmp_path.glob("*.tmp")) == []

    @pytest.mark.asyncio
    async def test_temp_names_are_unique_per_write(self, tmp_path: Path) -> None:
        """Имя временного файла не должно зависеть только от процесса."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session())
        seen: set[str] = set()
        real_replace = os.replace

        def _capture(src, dst):
            seen.add(Path(src).name)
            real_replace(src, dst)

        with patch("codelab.server.storage.json_file.os.replace", _capture):
            first = await storage.load_session("sess_x")
            assert first is not None
            await storage.save_session(first)
            second = await storage.load_session("sess_x")
            assert second is not None
            await storage.save_session(second)

        assert len(seen) == 2, f"временные имена совпали: {seen}"
