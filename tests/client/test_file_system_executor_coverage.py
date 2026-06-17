"""Дополнительные тесты для покрытия FileSystemExecutor.

Покрывает:
- обработку исключений при валидации пути
- ошибки чтения/записи async и sync методов
- полностью непокрытые sync методы
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from codelab.client.infrastructure.services.file_system_executor import FileSystemExecutor


class TestFileSystemExecutorPathValidationErrors:
    """Тесты для обработки ошибок в _validate_path."""

    @pytest.mark.asyncio
    async def test_validate_path_raises_on_invalid_path(self, tmp_path: Path) -> None:
        """_validate_path бросает ValueError при некорректном пути."""
        executor = FileSystemExecutor(base_path=tmp_path)

        # Null byte делает путь некорректным для Path.resolve
        with pytest.raises(ValueError, match="Invalid path"):
            executor._validate_path("file\x00.txt")


class TestFileSystemExecutorAsyncErrors:
    """Тесты для обработки ошибок в async методах."""

    @pytest.mark.asyncio
    async def test_read_text_file_raises_os_error_on_read_failure(
        self, tmp_path: Path
    ) -> None:
        """read_text_file оборачивает ошибку чтения в OSError."""
        test_file = tmp_path / "unreadable.txt"
        test_file.write_text("content")
        executor = FileSystemExecutor(base_path=tmp_path)

        with patch(
            "aiofiles.open",
            side_effect=PermissionError("denied"),
        ):
            with pytest.raises(OSError, match="Error reading file"):
                await executor.read_text_file("unreadable.txt")

    @pytest.mark.asyncio
    async def test_write_text_file_raises_os_error_on_write_failure(
        self, tmp_path: Path
    ) -> None:
        """write_text_file оборачивает ошибку записи в OSError."""
        executor = FileSystemExecutor(base_path=tmp_path)

        with patch(
            "aiofiles.open",
            side_effect=PermissionError("denied"),
        ):
            with pytest.raises(OSError, match="Error writing file"):
                await executor.write_text_file("nested/file.txt", "data")


class TestFileSystemExecutorSyncRead:
    """Тесты для синхронного чтения файлов."""

    def test_read_text_file_sync_full_file(self, tmp_path: Path) -> None:
        """read_text_file_sync читает весь файл."""
        test_file = tmp_path / "test.txt"
        content = "Line 1\nLine 2\nLine 3\n"
        test_file.write_text(content)

        executor = FileSystemExecutor(base_path=tmp_path)
        result = executor.read_text_file_sync("test.txt")

        assert result == content

    def test_read_text_file_sync_with_line_and_limit(self, tmp_path: Path) -> None:
        """read_text_file_sync поддерживает line и limit."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\n")

        executor = FileSystemExecutor(base_path=tmp_path)
        result = executor.read_text_file_sync("test.txt", line=2, limit=2)

        assert result == "Line 2\nLine 3\n"

    def test_read_text_file_sync_not_found(self, tmp_path: Path) -> None:
        """read_text_file_sync бросает FileNotFoundError для отсутствующего файла."""
        executor = FileSystemExecutor(base_path=tmp_path)

        with pytest.raises(FileNotFoundError, match="File not found"):
            executor.read_text_file_sync("missing.txt")

    def test_read_text_file_sync_directory(self, tmp_path: Path) -> None:
        """read_text_file_sync бросает ValueError при попытке читать директорию."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        executor = FileSystemExecutor(base_path=tmp_path)

        with pytest.raises(ValueError, match="Not a file"):
            executor.read_text_file_sync("subdir")

    def test_read_text_file_sync_raises_os_error(self, tmp_path: Path) -> None:
        """read_text_file_sync оборачивает ошибку чтения в OSError."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        executor = FileSystemExecutor(base_path=tmp_path)

        with patch("builtins.open", side_effect=PermissionError("denied")):
            with pytest.raises(OSError, match="Error reading file"):
                executor.read_text_file_sync("test.txt")


class TestFileSystemExecutorSyncWrite:
    """Тесты для синхронной записи файлов."""

    def test_write_text_file_sync_creates_file(self, tmp_path: Path) -> None:
        """write_text_file_sync создаёт файл и записывает содержимое."""
        executor = FileSystemExecutor(base_path=tmp_path)

        result = executor.write_text_file_sync("file.txt", "hello")

        assert result is True
        assert (tmp_path / "file.txt").read_text() == "hello"

    def test_write_text_file_sync_creates_parent_dirs(self, tmp_path: Path) -> None:
        """write_text_file_sync создаёт родительские директории."""
        executor = FileSystemExecutor(base_path=tmp_path)

        result = executor.write_text_file_sync("a/b/c/file.txt", "nested")

        assert result is True
        assert (tmp_path / "a" / "b" / "c" / "file.txt").read_text() == "nested"

    def test_write_text_file_sync_raises_os_error(self, tmp_path: Path) -> None:
        """write_text_file_sync оборачивает ошибку записи в OSError."""
        executor = FileSystemExecutor(base_path=tmp_path)

        with patch("builtins.open", side_effect=PermissionError("denied")):
            with pytest.raises(OSError, match="Error writing file"):
                executor.write_text_file_sync("file.txt", "data")

    def test_write_text_file_sync_empty_content(self, tmp_path: Path) -> None:
        """write_text_file_sync записывает пустой файл."""
        executor = FileSystemExecutor(base_path=tmp_path)

        result = executor.write_text_file_sync("empty.txt", "")

        assert result is True
        assert (tmp_path / "empty.txt").read_text() == ""


class TestFileSystemExecutorWithoutSandboxSync:
    """Тесты для sync методов без sandbox."""

    def test_read_text_file_sync_without_sandbox(self, tmp_path: Path) -> None:
        """read_text_file_sync работает с абсолютным путём без sandbox."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        executor = FileSystemExecutor()
        result = executor.read_text_file_sync(str(test_file))

        assert result == "content"

    def test_write_text_file_sync_without_sandbox(self, tmp_path: Path) -> None:
        """write_text_file_sync работает с абсолютным путём без sandbox."""
        test_file = tmp_path / "test.txt"
        executor = FileSystemExecutor()

        result = executor.write_text_file_sync(str(test_file), "content")

        assert result is True
        assert test_file.read_text() == "content"
