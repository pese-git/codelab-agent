"""Web UI управление — subprocess и HTML генерация.

Модуль отвечает за:
- Запуск/остановку textual-serve subprocess
- Генерацию HTML responses для Web UI
- Проверку доступности textual-web

Пример использования:
    manager = WebUIManager(host="127.0.0.1", port=8080)
    if manager.start_subprocess():
        response = manager.get_response()
    # ...
    manager.stop_subprocess()
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import structlog
from aiohttp import web

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class WebUIManager:
    """Управляет textual-serve subprocess и HTML responses.

    Инкапсулирует логику запуска subprocess, генерации HTML
    и управления жизненным циклом Web UI.

    Attributes:
        host: Хост основного сервера
        port: Порт основного сервера
    """

    def __init__(self, host: str, port: int) -> None:
        """Инициализирует WebUIManager.

        Args:
            host: Хост основного сервера
            port: Порт основного сервера
        """
        self.host = host
        self.port = port
        self._process: subprocess.Popen[bytes] | None = None
        self._web_ui_url: str | None = None

    @property
    def is_running(self) -> bool:
        """Проверяет, запущен ли subprocess."""
        return (
            self._process is not None
            and self._process.poll() is None
            and self._web_ui_url is not None
        )

    @property
    def web_ui_url(self) -> str | None:
        """Возвращает URL Web UI если subprocess запущен."""
        return self._web_ui_url if self.is_running else None

    def start_subprocess(self) -> bool:
        """Запускает textual-serve как subprocess для локального Web UI.

        Параметры передаются через переменные окружения — никакой интерполяции в код.

        Returns:
            True если subprocess успешно запущен, False иначе.
        """
        from codelab.server.web_app import is_web_ui_available

        if not is_web_ui_available():
            logger.debug("web_ui_not_started_textual_serve_unavailable")
            return False

        try:
            # Валидируем хост перед передачей в subprocess
            validated_host = self._validate_host(self.host)
            web_ui_port = self.port + 1000

            # Параметры передаются через env, не через f-string в код
            child_env = {
                **os.environ,
                "CODELAB_WS_HOST": validated_host,
                "CODELAB_WS_PORT": str(self.port),
                "CODELAB_WEB_UI_HOST": validated_host,
                "CODELAB_WEB_UI_PORT": str(web_ui_port),
            }

            self._process = subprocess.Popen(
                [sys.executable, "-m", "codelab.client.tui.serve_entry"],
                env=child_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            self._web_ui_url = f"http://{validated_host}:{web_ui_port}/"

            logger.info(
                "web_ui_subprocess_started",
                pid=self._process.pid,
                url=self._web_ui_url,
            )
            return True

        except Exception as e:
            logger.warning("failed_to_start_web_ui_subprocess", error=str(e))
            return False

    def stop_subprocess(self) -> None:
        """Останавливает subprocess с Web UI."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
                logger.info("web_ui_subprocess_stopped")
            except Exception as e:
                logger.warning("failed_to_stop_web_ui_subprocess", error=str(e))
                with contextlib.suppress(Exception):
                    self._process.kill()
            finally:
                self._process = None
                self._web_ui_url = None

    def get_response(self) -> web.Response:
        """Возвращает HTML response в зависимости от состояния subprocess.

        Returns:
            web.Response с HTML контентом
        """
        from codelab.server.web_app import get_fallback_html, is_web_ui_available

        if self.is_running:
            return self._get_iframe_html()
        elif is_web_ui_available():
            return self._get_manual_start_html()
        else:
            return self._get_fallback_html(get_fallback_html)

    def _validate_host(self, host: str) -> str:
        """Проверяет, что host — корректный IP или hostname.

        Args:
            host: Строка хоста для валидации

        Returns:
            Валидированный хост

        Raises:
            ValueError: Если хост некорректный
        """
        import ipaddress
        import re

        # Попытаться распарсить как IP
        try:
            ipaddress.ip_address(host)
            return host
        except ValueError:
            pass
        # Проверить как hostname (только буквы, цифры, дефисы, точки)
        if re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-\.]{0,253}[a-zA-Z0-9])?$', host):
            return host
        raise ValueError(f"Invalid host: {host!r}")

    def _get_iframe_html(self) -> web.Response:
        """Возвращает HTML с iframe для запущенного Web UI."""
        web_ui_url = self._web_ui_url
        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CodeLab - Web UI</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        html, body {{ height: 100%; overflow: hidden; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
        }}
        .loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #e4e4e4;
            text-align: center;
        }}
        .loading h2 {{ margin-bottom: 16px; color: #00d4ff; }}
        .spinner {{
            width: 40px;
            height: 40px;
            border: 3px solid #333;
            border-top-color: #00d4ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 16px;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        iframe {{
            width: 100%;
            height: 100%;
            border: none;
        }}
        .fallback-link {{
            margin-top: 24px;
            font-size: 0.875rem;
            color: #666;
        }}
        .fallback-link a {{ color: #00d4ff; }}
    </style>
</head>
<body>
    <div class="loading" id="loading">
        <div class="spinner"></div>
        <h2>🔬 CodeLab Web UI</h2>
        <p>Загрузка TUI интерфейса...</p>
        <p class="fallback-link">
            Не загружается? <a href="{web_ui_url}" target="_blank">Открыть напрямую</a>
        </p>
    </div>
    <iframe 
        id="webui" 
        src="{web_ui_url}"
        onload="document.getElementById('loading').style.display='none';"
        style="display: block;">
    </iframe>
</body>
</html>
"""
        return web.Response(text=html, content_type="text/html")

    def _get_manual_start_html(self) -> web.Response:
        """Возвращает HTML с инструкциями для ручного запуска Web UI."""
        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CodeLab - Web UI</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e4e4e4;
        }}
        .container {{
            max-width: 600px;
            padding: 40px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        h1 {{ font-size: 2rem; margin-bottom: 16px; color: #00d4ff; }}
        .status {{
            display: inline-block;
            padding: 4px 12px;
            background: #ffaa00;
            color: #1a1a2e;
            border-radius: 20px;
            font-size: 0.875rem;
            font-weight: 600;
            margin-bottom: 24px;
        }}
        p {{ line-height: 1.7; margin-bottom: 16px; color: #b4b4b4; }}
        pre {{
            background: #0d1117;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 16px 0;
        }}
        code {{ font-family: 'Fira Code', monospace; }}
        .url {{ color: #00ff88; }}
    </style>
</head>
<body>
    <div class="container">
        <span class="status">⚠️ Web UI не запущен</span>
        <h1>🔬 CodeLab</h1>
        <p>Textual Web установлен, но процесс Web UI не запустился.</p>
        <p>Запустите вручную (публикация через Ganglion):</p>
        <pre><code>textual-web --run \
"python -m codelab.client.tui.app --host {self.host} --port {self.port}"</code></pre>
        <p>Или используйте TUI клиент:</p>
        <pre><code>codelab connect --host {self.host} --port {self.port}</code></pre>
        <p>WebSocket endpoint: <span class="url">ws://{self.host}:{self.port}/acp/ws</span></p>
    </div>
</body>
</html>
"""
        return web.Response(text=html, content_type="text/html")

    def _get_fallback_html(self, get_fallback_html_fn) -> web.Response:
        """Возвращает fallback HTML когда textual-web не установлен."""
        html = get_fallback_html_fn(self.host, self.port)
        return web.Response(text=html, content_type="text/html")
