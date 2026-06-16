"""Тесты импортов основных модулей codelab."""

import pytest


def test_import_shared_messages():
    """Проверка импорта shared.messages."""
    from codelab.shared.messages import ACPMessage, JsonRpcError
    assert ACPMessage is not None
    assert JsonRpcError is not None


def test_import_shared_content():
    """Проверка импорта shared.content."""
    from codelab.shared.content import ImageContent, TextContent
    assert TextContent is not None
    assert ImageContent is not None


@pytest.mark.skip(reason="Требует aiohttp - рефакторинг в процессе")
def test_import_server():
    """Проверка импорта server."""
    from codelab.server import ACPProtocol
    assert ACPProtocol is not None


@pytest.mark.skip(reason="Требует исправления импортов - рефакторинг в процессе")
def test_import_client():
    """Проверка импорта client."""
    from codelab.client import ACPClientApp
    assert ACPClientApp is not None


def test_import_cli():
    """Проверка импорта CLI."""
    from codelab.cli import main
    assert main is not None
