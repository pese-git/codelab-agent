"""Тесты для CLI аргументов сервера."""

import contextlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from codelab.server.cli import describe_storage, parse_storage_arg, run_server
from codelab.server.storage import InMemoryStorage, JsonFileStorage


class TestCLIFallbackArgs:
    """Тесты для CLI аргументов fallback."""

    def test_fallback_enabled_arg(self) -> None:
        """Проверить что --fallback-enabled парсится."""
        test_args = ["codelab", "serve", "--fallback-enabled"]
        with (
            patch.object(sys, "argv", test_args),
            patch("codelab.server.cli.ACPHttpServer"),
            patch("codelab.server.cli.asyncio.run"),
            contextlib.suppress(SystemExit),
        ):
            run_server()

    def test_fallback_strategy_arg(self) -> None:
        """Проверить что --fallback-strategy парсится."""
        test_args = ["codelab", "serve", "--fallback-strategy", "sequential"]
        with (
            patch.object(sys, "argv", test_args),
            patch("codelab.server.cli.ACPHttpServer"),
            patch("codelab.server.cli.asyncio.run"),
            contextlib.suppress(SystemExit),
        ):
            run_server()

    def test_fallback_order_arg(self) -> None:
        """Проверить что --fallback-order парсится."""
        test_args = [
            "codelab",
            "serve",
            "--fallback-order",
            "openai,openrouter,ollama",
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("codelab.server.cli.ACPHttpServer"),
            patch("codelab.server.cli.asyncio.run"),
            contextlib.suppress(SystemExit),
        ):
            run_server()

    def test_all_fallback_args_combined(self) -> None:
        """Проверить все fallback аргументы вместе."""
        test_args = [
            "codelab",
            "serve",
            "--fallback-enabled",
            "--fallback-strategy",
            "sequential",
            "--fallback-order",
            "openai,anthropic,ollama",
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("codelab.server.cli.ACPHttpServer"),
            patch("codelab.server.cli.asyncio.run"),
            contextlib.suppress(SystemExit),
        ):
            run_server()


class TestParseStorageArg:
    """Тесты для parse_storage_arg()."""

    def test_memory_storage(self) -> None:
        """'memory' создаёт InMemoryStorage."""
        storage = parse_storage_arg("memory")
        assert isinstance(storage, InMemoryStorage)

    def test_json_storage_absolute_path(self) -> None:
        """'json:/path' создаёт JsonFileStorage."""
        storage = parse_storage_arg("json:/tmp/sessions")
        assert isinstance(storage, JsonFileStorage)
        assert storage.base_path == Path("/tmp/sessions")

    def test_json_storage_with_home_expansion(self) -> None:
        """'json:~/.codelab/sessions' расширяет ~."""
        storage = parse_storage_arg("json:~/.codelab/sessions")
        assert isinstance(storage, JsonFileStorage)
        assert "~" not in str(storage.base_path)

    def test_unknown_storage_raises(self) -> None:
        """Неизвестный формат вызывает ValueError."""
        with pytest.raises(ValueError, match="Unknown storage backend"):
            parse_storage_arg("redis://localhost")

    def test_unknown_storage_format_raises(self) -> None:
        """Другой неизвестный формат вызывает ValueError."""
        with pytest.raises(ValueError, match="Unknown storage backend"):
            parse_storage_arg("postgresql://localhost/db")


class TestDescribeStorage:
    """Тесты для describe_storage()."""

    def test_describe_memory(self) -> None:
        """InMemoryStorage описывается как 'memory'."""
        storage = InMemoryStorage()
        assert describe_storage(storage) == "memory"

    def test_describe_json_storage(self) -> None:
        """JsonFileStorage описывается как 'json:<path>'."""
        storage = JsonFileStorage(Path("/tmp/sessions"))
        description = describe_storage(storage)
        assert description.startswith("json:")
        assert "/tmp/sessions" in description

    def test_describe_json_storage_with_home(self) -> None:
        """JsonFileStorage с ~ описывается с полным путём."""
        storage = JsonFileStorage(Path.home() / ".codelab" / "sessions")
        description = describe_storage(storage)
        assert description.startswith("json:")
        assert "~" not in description
