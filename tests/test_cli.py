"""Тесты CLI."""

import subprocess
import sys


def test_cli_help():
    """Проверка вывода справки CLI."""
    result = subprocess.run(
        [sys.executable, "-m", "codelab.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "codelab" in result.stdout.lower()


def test_cli_serve_help():
    """Проверка справки команды serve."""
    result = subprocess.run(
        [sys.executable, "-m", "codelab.cli", "serve", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--port" in result.stdout
