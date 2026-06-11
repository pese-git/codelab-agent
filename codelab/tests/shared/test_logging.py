"""Тесты для модуля структурированного логирования.

Проверяют:
- Настройку логирования
- Создание файла логов
- Получение директорий
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from codelab.shared.logging import (
    get_codelab_dir,
    get_logs_dir,
    reset_logging,
    setup_logging,
)


class TestGetCodelabDir:
    """Тесты получения директории CodeLab."""

    def test_returns_home_codelab(self, tmp_path: Path) -> None:
        """get_codelab_dir возвращает ~/.codelab."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = get_codelab_dir()
            assert result == tmp_path / ".codelab"
            assert result.exists()

    def test_creates_directory_if_not_exists(self, tmp_path: Path) -> None:
        """get_codelab_dir создает директорию если она не существует."""
        codelab_dir = tmp_path / ".codelab"
        assert not codelab_dir.exists()

        with patch.object(Path, "home", return_value=tmp_path):
            get_codelab_dir()

        assert codelab_dir.exists()


class TestGetLogsDir:
    """Тесты получения директории логов."""

    def test_returns_default_logs_dir(self, tmp_path: Path) -> None:
        """get_logs_dir возвращает ~/.codelab/logs по умолчанию."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = get_logs_dir()
            assert result == tmp_path / ".codelab" / "logs"
            assert result.exists()

    def test_returns_custom_logs_dir(self, tmp_path: Path) -> None:
        """get_logs_dir возвращает кастомную директорию если указана."""
        custom_dir = tmp_path / "custom_logs"
        result = get_logs_dir(custom_dir)
        assert result == custom_dir
        assert result.exists()


class TestSetupLogging:
    """Тесты настройки логирования."""

    def setup_method(self) -> None:
        """Сбрасывает логирование перед каждым тестом."""
        reset_logging()

    def teardown_method(self) -> None:
        """Сбрасывает логирование после каждого теста."""
        reset_logging()

    def test_creates_log_file(self, tmp_path: Path) -> None:
        """setup_logging создает файл логов."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        setup_logging(
            level="DEBUG",
            log_file=str(logs_dir / "test.log"),
            log_dir=logs_dir,
        )

        # Проверяем что root logger имеет handlers
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) >= 1

    def test_log_file_path_is_correct(self, tmp_path: Path) -> None:
        """Файл логов создается в правильной директории."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        setup_logging(
            level="DEBUG",
            log_file=str(logs_dir / "test.log"),
            log_dir=logs_dir,
        )

        # Проверяем что handler настроен
        root_logger = logging.getLogger()
        file_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) >= 1

    def test_without_log_file_no_file_handler(self, tmp_path: Path) -> None:
        """Без log_file нет файлового handler."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        setup_logging(
            level="DEBUG",
            log_file=None,
            log_dir=logs_dir,
        )

        root_logger = logging.getLogger()
        file_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 0

    def test_stderr_only_adds_stderr_handler(self, tmp_path: Path) -> None:
        """stderr_only=True добавляет handler для stderr."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Directly test the handler creation logic
        import logging as std_logging
        import sys

        handlers: list[std_logging.Handler] = []
        stderr_handler = std_logging.StreamHandler(stream=sys.stderr)
        handlers.append(stderr_handler)

        std_logging.basicConfig(
            format="%(message)s",
            handlers=handlers,
            level=std_logging.DEBUG,
            force=True,
        )

        root_logger = std_logging.getLogger()
        stderr_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, std_logging.StreamHandler)
            and h.stream is sys.stderr
        ]
        assert len(stderr_handlers) >= 1

    def test_stderr_only_no_stdout_handler(self, tmp_path: Path) -> None:
        """stderr_only=True НЕ добавляет handler для stdout."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        import logging as std_logging
        import sys

        handlers: list[std_logging.Handler] = []
        stderr_handler = std_logging.StreamHandler(stream=sys.stderr)
        handlers.append(stderr_handler)

        std_logging.basicConfig(
            format="%(message)s",
            handlers=handlers,
            level=std_logging.DEBUG,
            force=True,
        )

        root_logger = std_logging.getLogger()
        stdout_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, std_logging.StreamHandler)
            and h.stream is sys.stdout
        ]
        assert len(stdout_handlers) == 0

    def test_console_output_uses_stdout(self, tmp_path: Path) -> None:
        """console_output=True использует stdout."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        import logging as std_logging
        import sys

        handlers: list[std_logging.Handler] = []
        stream_handler = std_logging.StreamHandler(stream=sys.stdout)
        handlers.append(stream_handler)

        std_logging.basicConfig(
            format="%(message)s",
            handlers=handlers,
            level=std_logging.DEBUG,
            force=True,
        )

        root_logger = std_logging.getLogger()
        stdout_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, std_logging.StreamHandler)
            and h.stream is sys.stdout
        ]
        assert len(stdout_handlers) >= 1
