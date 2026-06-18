"""Тесты покрытия непокрытых веток JsonFileStorage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codelab.server.exceptions import StorageError
from codelab.server.protocol.state import SessionState
from codelab.server.storage.json_file import JsonFileStorage


@pytest.fixture
def storage(tmp_path: Path) -> JsonFileStorage:
    """Создаёт JSON файловое хранилище во временной директории."""
    return JsonFileStorage(tmp_path)


class TestJsonFileStorageSaveErrors:
    """Тесты обработки ошибок сохранения."""

    @pytest.mark.asyncio
    async def test_save_session_write_error(
        self,
        storage: JsonFileStorage,
    ) -> None:
        """Ошибка записи файла оборачивается в StorageError (строки 74-75)."""
        session = SessionState(session_id="s1", cwd="/tmp", mcp_servers=[])

        with patch(
            "codelab.server.storage.json_file.aiofiles.open",
            side_effect=PermissionError("denied"),
        ):
            with pytest.raises(StorageError, match="Failed to save session s1"):
                await storage.save_session(session)


class TestJsonFileStorageLoadErrors:
    """Тесты обработки ошибок загрузки."""

    @pytest.mark.asyncio
    async def test_load_session_validation_error(
        self,
        storage: JsonFileStorage,
        tmp_path: Path,
    ) -> None:
        """Невалидные данные сессии оборачиваются в StorageError (строки 108-109)."""
        file_path = tmp_path / "s1.json"
        file_path.write_text('{"session_id": "s1", "cwd": 123}')

        with pytest.raises(StorageError, match="Invalid session data s1"):
            await storage.load_session("s1")

    @pytest.mark.asyncio
    async def test_load_session_unexpected_error(
        self,
        storage: JsonFileStorage,
        tmp_path: Path,
    ) -> None:
        """Непредвиденная ошибка загрузки оборачивается в StorageError (строки 110-111)."""
        file_path = tmp_path / "s1.json"
        file_path.write_text('{}')

        with patch(
            "codelab.server.storage.json_file.aiofiles.open",
            side_effect=RuntimeError("read boom"),
        ):
            with pytest.raises(StorageError, match="Failed to load session s1"):
                await storage.load_session("s1")


class TestJsonFileStorageDeleteErrors:
    """Тесты обработки ошибок удаления."""

    @pytest.mark.asyncio
    async def test_delete_session_unlink_error(
        self,
        storage: JsonFileStorage,
        tmp_path: Path,
    ) -> None:
        """Ошибка удаления файла оборачивается в StorageError (строки 131-132)."""
        file_path = tmp_path / "s1.json"
        file_path.write_text('{}')

        with patch.object(Path, "unlink", side_effect=OSError("unlink failed")):
            with pytest.raises(StorageError, match="Failed to delete session s1"):
                await storage.delete_session("s1")


class TestJsonFileStorageListErrors:
    """Тесты обработки ошибок получения списка сессий."""

    @pytest.mark.asyncio
    async def test_list_sessions_glob_error(
        self,
        storage: JsonFileStorage,
    ) -> None:
        """Ошибка чтения директории оборачивается в StorageError (строки 184-185)."""
        mock_path = MagicMock()
        mock_path.glob.side_effect = OSError("glob failed")

        with patch.object(storage, "base_path", mock_path):
            with pytest.raises(StorageError, match="Failed to list sessions"):
                await storage.list_sessions()
