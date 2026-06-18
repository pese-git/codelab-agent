"""Тесты для FsCallbackExecutor."""

from __future__ import annotations

from pathlib import Path

import pytest

from codelab.client.presentation.chat.executors.fs_callback_executor import (
    FsCallbackExecutor,
)


class TestFsCallbackExecutor:
    """Тесты для FsCallbackExecutor."""

    @pytest.fixture
    def temp_dir(self, tmp_path: Path) -> Path:
        """Создаёт временную директорию для тестов."""
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True)
        return workspace

    @pytest.fixture
    def executor(self, temp_dir: Path) -> FsCallbackExecutor:
        """Создаёт экземпляр FsCallbackExecutor для тестов."""
        return FsCallbackExecutor(temp_dir)

    def test_init_with_valid_directory(self, temp_dir: Path) -> None:
        """Инициализация должна работать с валидной директорией."""
        executor = FsCallbackExecutor(temp_dir)
        assert executor._base_path == temp_dir.resolve()

    def test_init_with_nonexistent_directory(self, tmp_path: Path) -> None:
        """Инициализация должна вызывать ошибку для несуществующей директории."""
        nonexistent = tmp_path / "nonexistent"
        with pytest.raises(ValueError, match="does not exist"):
            FsCallbackExecutor(nonexistent)

    def test_init_with_file_instead_of_directory(self, tmp_path: Path) -> None:
        """Инициализация должна вызывать ошибку если путь является файлом."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")
        with pytest.raises(ValueError, match="not a directory"):
            FsCallbackExecutor(file_path)

    def test_validate_path_relative(self, executor: FsCallbackExecutor) -> None:
        """_validate_path должен корректно обрабатывать относительные пути."""
        validated = executor._validate_path("test.txt")
        assert str(validated).startswith(str(executor._base_path))
        assert validated.name == "test.txt"

    def test_validate_path_absolute_within_sandbox(
        self, executor: FsCallbackExecutor
    ) -> None:
        """_validate_path должен принимать абсолютные пути в пределах sandbox."""
        abs_path = executor._base_path / "test.txt"
        validated = executor._validate_path(str(abs_path))
        assert validated == abs_path

    def test_validate_path_traversal_attack(self, executor: FsCallbackExecutor) -> None:
        """_validate_path должен блокировать path traversal атаки."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            executor._validate_path("../../etc/passwd")

    def test_validate_path_absolute_outside_sandbox(
        self, executor: FsCallbackExecutor
    ) -> None:
        """_validate_path должен блокировать абсолютные пути вне sandbox."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            executor._validate_path("/etc/passwd")

    @pytest.mark.asyncio
    async def test_read_file_success(self, executor: FsCallbackExecutor) -> None:
        """read_file должен успешно читать существующий файл."""
        # Создаём тестовый файл
        test_file = executor._base_path / "test.txt"
        test_file.write_text("Hello, World!", encoding="utf-8")

        content, error = await executor.read_file("test.txt")

        assert content == "Hello, World!"
        assert error is None

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, executor: FsCallbackExecutor) -> None:
        """read_file должен возвращать ошибку для несуществующего файла."""
        content, error = await executor.read_file("nonexistent.txt")

        assert content is None
        assert error is not None
        assert "not found" in error.lower()

    @pytest.mark.asyncio
    async def test_read_file_path_traversal(
        self, executor: FsCallbackExecutor
    ) -> None:
        """read_file должен блокировать path traversal."""
        content, error = await executor.read_file("../../etc/passwd")

        assert content is None
        assert error is not None
        assert "path validation" in error.lower()

    @pytest.mark.asyncio
    async def test_read_file_is_directory(
        self, executor: FsCallbackExecutor
    ) -> None:
        """read_file должен возвращать ошибку если путь является директорией."""
        # Создаём поддиректорию
        subdir = executor._base_path / "subdir"
        subdir.mkdir()

        content, error = await executor.read_file("subdir")

        assert content is None
        assert error is not None
        assert "directory" in error.lower()

    @pytest.mark.asyncio
    async def test_write_file_success(self, executor: FsCallbackExecutor) -> None:
        """write_file должен успешно записывать файл."""
        success, error = await executor.write_file("test.txt", "Hello, World!")

        assert success is True
        assert error is None

        # Проверяем что файл действительно записан
        test_file = executor._base_path / "test.txt"
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == "Hello, World!"

    @pytest.mark.asyncio
    async def test_write_file_creates_parent_directories(
        self, executor: FsCallbackExecutor
    ) -> None:
        """write_file должен создавать родительские директории."""
        success, error = await executor.write_file(
            "subdir/nested/test.txt", "Content"
        )

        assert success is True
        assert error is None

        test_file = executor._base_path / "subdir" / "nested" / "test.txt"
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == "Content"

    @pytest.mark.asyncio
    async def test_write_file_path_traversal(
        self, executor: FsCallbackExecutor
    ) -> None:
        """write_file должен блокировать path traversal."""
        success, error = await executor.write_file("../../etc/passwd", "malicious")

        assert success is False
        assert error is not None
        assert "path validation" in error.lower()

    @pytest.mark.asyncio
    async def test_write_file_unicode(self, executor: FsCallbackExecutor) -> None:
        """write_file должен корректно записывать Unicode."""
        success, error = await executor.write_file("unicode.txt", "Привет, мир!")

        assert success is True
        assert error is None

        test_file = executor._base_path / "unicode.txt"
        assert test_file.read_text(encoding="utf-8") == "Привет, мир!"

    @pytest.mark.asyncio
    async def test_read_write_round_trip(
        self, executor: FsCallbackExecutor
    ) -> None:
        """Полный цикл write/read должен сохранять данные."""
        # Используем только \n и \t, так как \r может конвертироваться
        content = "Test content with special chars: \n\t"

        write_success, write_error = await executor.write_file("roundtrip.txt", content)
        assert write_success is True
        assert write_error is None

        read_content, read_error = await executor.read_file("roundtrip.txt")
        assert read_content == content
        assert read_error is None
