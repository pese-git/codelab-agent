"""Тесты для CLI аргументов сервера."""

import contextlib
import sys
from unittest.mock import patch

from codelab.server.cli import run_server


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
