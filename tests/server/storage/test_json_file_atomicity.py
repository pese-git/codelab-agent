"""Запись сессии атомарна (ADR-007).

Прямая запись в целевой файл оставляла обрезанный документ при падении посреди
записи или при двух писателях, а сессия уже занимает сотни килобайт (замер:
751 КБ на 53 вызова). Читатель обязан видеть либо прежний документ целиком, либо
новый целиком.
"""

from __future__ import annotations

import json
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

        await storage.save_session(_session("/second"))

        raw = json.loads((tmp_path / "sess_x.json").read_text(encoding="utf-8"))
        assert raw["cwd"] == "/second"
        assert list(tmp_path.glob("*.tmp")) == []

    @pytest.mark.asyncio
    async def test_document_is_never_partially_visible(self, tmp_path: Path) -> None:
        """Пока идёт запись, читатель видит прежний документ, а не полуфабрикат."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session("/first"))
        seen: list[str] = []

        real_replace = __import__("os").replace

        def _peek_then_replace(src, dst):
            # В момент между записью tmp и подменой целевого файла
            loaded = json.loads(Path(dst).read_text(encoding="utf-8"))
            seen.append(loaded["cwd"])
            real_replace(src, dst)

        with patch("codelab.server.storage.json_file.os.replace", _peek_then_replace):
            await storage.save_session(_session("/second"))

        assert seen == ["/first"]
        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.cwd == "/second"
