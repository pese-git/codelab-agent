"""Дополнительные тесты для покрытия непокрытых веток GlobalPolicyStorage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from codelab.server.exceptions import StorageError
from codelab.server.storage import GlobalPolicyStorage


class TestGlobalPolicyStorageReadErrors:
    """Тесты обработки ошибок чтения файла."""

    @pytest.mark.asyncio
    async def test_load_oserror_on_existing_path(self, tmp_path: Path) -> None:
        """Ошибка чтения существующего файла оборачивается в StorageError."""
        policy_path = tmp_path / "policies.json"
        policy_path.mkdir()

        storage = GlobalPolicyStorage(policy_path)

        with pytest.raises(StorageError, match="Cannot read policy file"):
            await storage.load()

    @pytest.mark.asyncio
    async def test_load_unexpected_error(self, tmp_path: Path) -> None:
        """Неожиданная ошибка при загрузке оборачивается в StorageError."""
        storage = GlobalPolicyStorage(tmp_path / "policies.json")

        with patch.object(
            storage,
            "_read_file",
            new=AsyncMock(side_effect=RuntimeError("unexpected boom")),
        ):
            with pytest.raises(StorageError, match="Unexpected error loading policies"):
                await storage.load()


class TestGlobalPolicyStorageVersionMismatch:
    """Тесты обработки несовпадения версии схемы."""

    @pytest.mark.asyncio
    async def test_load_version_mismatch_logs_warning(self, tmp_path: Path) -> None:
        """Несовпадение версии схемы логирует предупреждение и возвращает policies."""
        policy_path = tmp_path / "policies.json"
        policy_path.write_text(
            json.dumps(
                {
                    "version": 999,
                    "policies": {"execute": "allow_always"},
                    "metadata": {},
                }
            )
        )

        storage = GlobalPolicyStorage(policy_path)

        with patch("codelab.server.storage.global_policy_storage.logger") as mock_logger:
            policies = await storage.load()

        assert policies == {"execute": "allow_always"}
        mock_logger.warning.assert_called_once_with(
            "policy_version_mismatch",
            file_version=999,
            expected_version=GlobalPolicyStorage.SCHEMA_VERSION,
        )


class TestGlobalPolicyStorageWriteErrors:
    """Тесты обработки ошибок записи файла."""

    @pytest.mark.asyncio
    async def test_save_write_file_oserror(self, tmp_path: Path) -> None:
        """Ошибка записи файла (OSError) оборачивается в StorageError."""
        storage = GlobalPolicyStorage(tmp_path / "policies.json")

        with patch(
            "codelab.server.storage.global_policy_storage.aiofiles.open",
            side_effect=PermissionError("denied"),
        ):
            with pytest.raises(StorageError, match="Cannot write policy file"):
                await storage.save({"execute": "allow_always"})

    @pytest.mark.asyncio
    async def test_save_write_file_unexpected_error(self, tmp_path: Path) -> None:
        """Неожиданная ошибка записи файла оборачивается в StorageError."""
        storage = GlobalPolicyStorage(tmp_path / "policies.json")

        with patch(
            "codelab.server.storage.global_policy_storage.aiofiles.open",
            side_effect=RuntimeError("write boom"),
        ):
            with pytest.raises(StorageError, match="Unexpected error writing policy file"):
                await storage.save({"execute": "allow_always"})


class TestGlobalPolicyStorageSaveErrors:
    """Тесты обработки ошибок в методе save."""

    @pytest.mark.asyncio
    async def test_save_propagates_storage_error(self, tmp_path: Path) -> None:
        """StorageError из _write_file пробрасывается без изменений."""
        storage = GlobalPolicyStorage(tmp_path / "policies.json")

        with patch.object(
            storage,
            "_write_file",
            new=AsyncMock(side_effect=StorageError("disk full")),
        ):
            with pytest.raises(StorageError, match="disk full"):
                await storage.save({"execute": "allow_always"})

    @pytest.mark.asyncio
    async def test_save_unexpected_error(self, tmp_path: Path) -> None:
        """Неожиданная ошибка в save оборачивается в StorageError."""
        storage = GlobalPolicyStorage(tmp_path / "policies.json")

        with patch.object(
            storage,
            "_write_file",
            new=AsyncMock(side_effect=RuntimeError("save boom")),
        ):
            with pytest.raises(StorageError, match="Unexpected error saving policies"):
                await storage.save({"execute": "allow_always"})
