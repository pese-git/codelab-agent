"""Тесты покрытия для codelab.server.web_app.

Покрывает все HTTP-helpers Web UI: проверку доступности, создание конфигурации
и fallback HTML-страницу.
"""

from __future__ import annotations

import importlib
import importlib.util
from unittest.mock import patch

import pytest

import codelab.server.web_app as web_app
from codelab.server.web_app import create_web_app, get_fallback_html, is_web_ui_available


class TestModuleImport:
    """Тесты поведения модуля при импорте."""

    def test_logs_not_available_when_textual_serve_missing(self) -> None:
        """При отсутствии textual-serve флаг выставляется в False."""
        original_available = web_app.TEXTUAL_SERVE_AVAILABLE
        try:
            with patch("importlib.util.find_spec", return_value=None):
                importlib.reload(web_app)

            assert web_app.TEXTUAL_SERVE_AVAILABLE is False
        finally:
            with patch(
                "importlib.util.find_spec",
                return_value=importlib.util.find_spec("textual_serve"),
            ):
                importlib.reload(web_app)
            assert original_available == web_app.TEXTUAL_SERVE_AVAILABLE


class TestIsWebUiAvailable:
    """Тесты is_web_ui_available."""

    def test_returns_true_when_textual_serve_available(self) -> None:
        """Возвращает True, если textual-serve установлен."""
        with patch.object(web_app, "TEXTUAL_SERVE_AVAILABLE", True):
            assert is_web_ui_available() is True

    def test_returns_false_when_textual_serve_not_available(self) -> None:
        """Возвращает False, если textual-serve не установлен."""
        with patch.object(web_app, "TEXTUAL_SERVE_AVAILABLE", False):
            assert is_web_ui_available() is False


class TestCreateWebApp:
    """Тесты create_web_app."""

    def test_raises_when_textual_serve_not_available(self) -> None:
        """RuntimeError, если textual-serve не установлен."""
        with patch.object(web_app, "TEXTUAL_SERVE_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="textual-serve не установлен"):
                create_web_app()

    def test_default_server_url(self) -> None:
        """По умолчанию использует ws://localhost:8765/acp/ws."""
        with patch.object(web_app, "TEXTUAL_SERVE_AVAILABLE", True):
            config = create_web_app()

        assert config == {
            "host": "localhost",
            "port": 8765,
            "server_url": "ws://localhost:8765/acp/ws",
        }

    def test_custom_server_url(self) -> None:
        """Извлекает host и port из переданного URL."""
        with patch.object(web_app, "TEXTUAL_SERVE_AVAILABLE", True):
            config = create_web_app("ws://example.com:9999/acp/ws")

        assert config == {
            "host": "example.com",
            "port": 9999,
            "server_url": "ws://example.com:9999/acp/ws",
        }

    def test_wss_url(self) -> None:
        """Поддерживает wss:// URL."""
        with patch.object(web_app, "TEXTUAL_SERVE_AVAILABLE", True):
            config = create_web_app("wss://secure.host:1234/acp/ws")

        assert config["host"] == "secure.host"
        assert config["port"] == 1234
        assert config["server_url"] == "wss://secure.host:1234/acp/ws"

    def test_invalid_url_uses_defaults(self) -> None:
        """Некорректный URL использует значения по умолчанию."""
        with patch.object(web_app, "TEXTUAL_SERVE_AVAILABLE", True):
            config = create_web_app("not-a-valid-url")

        assert config["host"] == "localhost"
        assert config["port"] == 8765
        assert config["server_url"] == "not-a-valid-url"


class TestGetFallbackHtml:
    """Тесты get_fallback_html."""

    def test_substitutes_host_and_port(self) -> None:
        """HTML содержит переданный host и port."""
        html = get_fallback_html("myhost", 1234)

        assert "ws://myhost:1234/acp/ws" in html
        assert "codelab serve --port 1234" in html
        assert "codelab connect --host myhost --port 1234" in html

    def test_contains_install_instructions(self) -> None:
        """HTML содержит инструкции по установке."""
        html = get_fallback_html("localhost", 8765)

        assert "pip install 'codelab[web]'" in html
        assert "pip install textual-web" in html

    def test_contains_russian_title(self) -> None:
        """HTML содержит русский заголовок."""
        html = get_fallback_html("localhost", 8765)

        assert "CodeLab - Web UI недоступен" in html
