"""Тесты покрытия для src/codelab/cli.py.

Покрывают функции CLI, которые не были протестированы в tests/test_cli.py:
создание домашней директории, настройку логирования, парсинг аргументов,
запуск режимов serve/connect/local и вспомогательные утилиты.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import codelab.cli as cli_module
from codelab.cli import (
    _configure_logging,
    _get_log_level_for_serve,
    _run_tui_app,
    ensure_home_directory,
    main,
    run_connect,
    run_local,
    run_serve,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch


class TestEnsureHomeDirectory:
    """Тесты для ensure_home_directory()."""

    def test_creates_directories_and_env(self, monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
        """Создаёт структуру директорий и шаблон .env при первом запуске."""
        monkeypatch.setattr(cli_module, "CODELAB_HOME", tmp_path)

        ensure_home_directory()

        assert (tmp_path / "config").is_dir()
        assert (tmp_path / "logs").is_dir()
        assert (tmp_path / "data" / "sessions").is_dir()
        assert (tmp_path / "data" / "history").is_dir()
        assert (tmp_path / "data" / "policies").is_dir()
        assert (tmp_path / "cache").is_dir()
        assert (tmp_path / "config" / ".env").exists()
        env_content = (tmp_path / "config" / ".env").read_text(encoding="utf-8")
        assert "CODELAB_LLM_PROVIDER" in env_content

    def test_skips_env_when_toml_exists(self, monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
        """Не создаёт .env, если в домашней директории уже есть codelab.toml."""
        monkeypatch.setattr(cli_module, "CODELAB_HOME", tmp_path)
        (tmp_path / "codelab.toml").write_text("[codelab]\n")

        ensure_home_directory()

        assert (tmp_path / "config").is_dir()
        assert not (tmp_path / "config" / ".env").exists()

    def test_skips_env_when_already_exists(self, monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
        """Не перезаписывает существующий config/.env файл."""
        monkeypatch.setattr(cli_module, "CODELAB_HOME", tmp_path)
        (tmp_path / "config").mkdir(parents=True)
        existing = "EXISTING=1\n"
        (tmp_path / "config" / ".env").write_text(existing, encoding="utf-8")

        ensure_home_directory()

        assert (tmp_path / "config" / ".env").read_text(encoding="utf-8") == existing


class TestConfigureLogging:
    """Тесты для _configure_logging()."""

    def test_uses_verbose_debug(self, monkeypatch: MonkeyPatch) -> None:
        """При verbose=True используется уровень DEBUG."""
        calls: list[dict[str, object]] = []
        monkeypatch.setattr(
            "codelab.shared.logging.setup_logging",
            lambda **kwargs: calls.append(kwargs),
        )

        _configure_logging(verbose=True, console_output=False)

        assert calls[0]["level"] == "DEBUG"
        assert calls[0]["json_format"] is False
        assert calls[0]["log_file"] == "default"
        assert calls[0]["console_output"] is False

    def test_uses_env_log_level(self, monkeypatch: MonkeyPatch) -> None:
        """Без verbose используется CODELAB_LOG_LEVEL из окружения."""
        calls: list[dict[str, object]] = []
        monkeypatch.setattr(
            "codelab.shared.logging.setup_logging",
            lambda **kwargs: calls.append(kwargs),
        )
        monkeypatch.setenv("CODELAB_LOG_LEVEL", "WARNING")

        _configure_logging(verbose=False, console_output=True)

        assert calls[0]["level"] == "WARNING"
        assert calls[0]["console_output"] is True


class TestGetLogLevelForServe:
    """Тесты для _get_log_level_for_serve()."""

    def test_log_level_arg_highest_priority(self) -> None:
        """Аргумент --log-level имеет высший приоритет."""
        args = argparse.Namespace(log_level="ERROR", verbose=True)
        assert _get_log_level_for_serve(args) == "ERROR"

    def test_verbose_fallback(self) -> None:
        """При verbose=True возвращается DEBUG, если --log-level не указан."""
        args = argparse.Namespace(log_level=None, verbose=True)
        assert _get_log_level_for_serve(args) == "DEBUG"

    def test_env_fallback(self, monkeypatch: MonkeyPatch) -> None:
        """Без флагов используется значение переменной окружения."""
        monkeypatch.setenv("CODELAB_LOG_LEVEL", "WARNING")
        args = argparse.Namespace(log_level=None, verbose=False)
        assert _get_log_level_for_serve(args) == "WARNING"

    def test_default_info(self, monkeypatch: MonkeyPatch) -> None:
        """По умолчанию возвращается INFO."""
        monkeypatch.delenv("CODELAB_LOG_LEVEL", raising=False)
        args = argparse.Namespace(log_level=None, verbose=False)
        assert _get_log_level_for_serve(args) == "INFO"


class TestRunLocal:
    """Тесты для run_local()."""

    def test_starts_tui_with_stdio(self, monkeypatch: MonkeyPatch) -> None:
        """Локальный режим запускает TUI через stdio транспорт."""
        captured: dict[str, object] = {}
        monkeypatch.setattr(
            "codelab.cli._run_tui_app",
            lambda **kwargs: captured.update(kwargs),
        )
        args = argparse.Namespace(verbose=False)

        run_local(args)

        assert captured["host"] == "127.0.0.1"
        assert captured["port"] == cli_module.DEFAULT_PORT
        assert captured["transport_mode"] == "stdio"
        assert captured["stdio_command"] == "codelab"
        assert captured["stdio_args"] == ["serve", "--stdio"]


class TestRunConnect:
    """Тесты для run_connect()."""

    def test_websocket_mode(self, monkeypatch: MonkeyPatch) -> None:
        """Режим connect через WebSocket передаёт host/port/theme/timeout."""
        captured: dict[str, object] = {}
        monkeypatch.setattr(
            "codelab.cli._run_tui_app",
            lambda **kwargs: captured.update(kwargs),
        )
        args = argparse.Namespace(
            host="remote.example.com",
            port=4096,
            cwd="/tmp/project",
            stdio=False,
            agent_command=None,
            theme="dark",
        )

        run_connect(args)

        assert captured["host"] == "remote.example.com"
        assert captured["port"] == 4096
        assert captured["cwd"] == "/tmp/project"
        # websocket режим не передаёт transport_mode явно, используется default
        assert "stdio_command" not in captured
        assert captured["theme"] == "dark"

    def test_stdio_mode_appends_stdio_flag(self, monkeypatch: MonkeyPatch) -> None:
        """Stdio режим добавляет --stdio к команде агента."""
        captured: dict[str, object] = {}
        monkeypatch.setattr(
            "codelab.cli._run_tui_app",
            lambda **kwargs: captured.update(kwargs),
        )
        args = argparse.Namespace(
            host="127.0.0.1",
            port=cli_module.DEFAULT_PORT,
            cwd="/tmp/project",
            stdio=True,
            agent_command="python -m codelab.cli serve",
            theme=None,
        )

        run_connect(args)

        assert captured["transport_mode"] == "stdio"
        assert captured["stdio_command"] == "python"
        assert captured["stdio_args"] == ["-m", "codelab.cli", "serve", "--stdio"]
        assert captured["cwd"] == "/tmp/project"

    def test_stdio_mode_defaults_to_codelab(self, monkeypatch: MonkeyPatch) -> None:
        """Без --agent-command используется 'codelab' по умолчанию."""
        captured: dict[str, object] = {}
        monkeypatch.setattr(
            "codelab.cli._run_tui_app",
            lambda **kwargs: captured.update(kwargs),
        )
        args = argparse.Namespace(
            host="127.0.0.1",
            port=cli_module.DEFAULT_PORT,
            cwd=None,
            stdio=True,
            agent_command=None,
            theme=None,
            receive_timeout=None,
        )

        run_connect(args)

        assert captured["stdio_command"] == "codelab"
        assert captured["stdio_args"] == ["--stdio"]


class TestRunServe:
    """Тесты для run_serve()."""

    def test_websocket_mode(self, monkeypatch: MonkeyPatch) -> None:
        """WebSocket режим создаёт ACPHttpServer и запускает его."""
        server_mock = MagicMock()
        server_mock.run = AsyncMock()
        run_calls: list[object] = []

        def make_server(**kwargs: object) -> MagicMock:
            for key, value in kwargs.items():
                setattr(server_mock, key, value)
            return server_mock

        monkeypatch.setattr(
            "codelab.server.http_server.ACPHttpServer",
            make_server,
        )
        monkeypatch.setattr(
            "codelab.server.storage.json_file.JsonFileStorage",
            lambda path: "storage",
        )
        monkeypatch.setattr(
            "codelab.server.config.AppConfig.from_env",
            classmethod(lambda cls: "config"),
        )
        monkeypatch.setattr(
            "codelab.cli.asyncio.run",
            lambda coro: run_calls.append(coro),
        )
        monkeypatch.setattr("codelab.shared.logging.setup_logging", lambda **kwargs: None)

        args = argparse.Namespace(
            host="0.0.0.0",
            port=4096,
            stdio=False,
            no_web=True,
            trace_messages=True,
            require_auth=True,
            log_level="DEBUG",
            verbose=False,
        )

        run_serve(args)

        assert len(run_calls) == 1
        assert server_mock.run.call_count == 1
        assert server_mock.host == "0.0.0.0"
        assert server_mock.port == 4096
        assert server_mock.enable_web is False
        assert server_mock.trace_messages is True
        assert server_mock.require_auth is True
        assert server_mock.storage == "storage"
        assert server_mock.config == "config"

    def test_stdio_mode(self, monkeypatch: MonkeyPatch) -> None:
        """Stdio режим запускает run_stdio_server."""
        run_stdio_mock = AsyncMock()
        run_calls: list[object] = []
        monkeypatch.setattr(
            "codelab.server.transport.stdio_runner.run_stdio_server",
            run_stdio_mock,
        )
        monkeypatch.setattr(
            "codelab.server.storage.json_file.JsonFileStorage",
            lambda path: "storage",
        )
        monkeypatch.setattr(
            "codelab.server.config.AppConfig.from_env",
            classmethod(lambda cls: "config"),
        )
        monkeypatch.setattr(
            "codelab.cli.asyncio.run",
            lambda coro: run_calls.append(coro),
        )
        monkeypatch.setattr("codelab.shared.logging.setup_logging", lambda **kwargs: None)

        args = argparse.Namespace(
            host="127.0.0.1",
            port=cli_module.DEFAULT_PORT,
            stdio=True,
            no_web=False,
            trace_messages=False,
            require_auth=False,
            log_level=None,
            verbose=False,
        )

        run_serve(args)

        assert len(run_calls) == 1
        run_stdio_mock.assert_called_once_with(
            storage="storage",
            config="config",
            require_auth=False,
            auth_api_key=None,
            trace_messages=False,
        )

    def test_uses_auth_api_key_from_env(self, monkeypatch: MonkeyPatch) -> None:
        """Передаёт ACP_SERVER_API_KEY в сервер."""
        server_mock = MagicMock()
        server_mock.run = AsyncMock()

        def make_server(**kwargs: object) -> MagicMock:
            for key, value in kwargs.items():
                setattr(server_mock, key, value)
            return server_mock

        monkeypatch.setattr(
            "codelab.server.http_server.ACPHttpServer",
            make_server,
        )
        monkeypatch.setattr(
            "codelab.server.storage.json_file.JsonFileStorage",
            lambda path: "storage",
        )
        monkeypatch.setattr(
            "codelab.server.config.AppConfig.from_env",
            classmethod(lambda cls: "config"),
        )
        monkeypatch.setattr("codelab.cli.asyncio.run", lambda coro: coro)
        monkeypatch.setattr("codelab.shared.logging.setup_logging", lambda **kwargs: None)
        monkeypatch.setenv("ACP_SERVER_API_KEY", "secret-key")

        args = argparse.Namespace(
            host="127.0.0.1",
            port=cli_module.DEFAULT_PORT,
            stdio=False,
            no_web=False,
            trace_messages=False,
            require_auth=True,
            log_level=None,
            verbose=False,
        )

        run_serve(args)

        assert server_mock.auth_api_key == "secret-key"

    def test_keyboard_interrupt_websocket(self, monkeypatch: MonkeyPatch) -> None:
        """KeyboardInterrupt в WebSocket режиме обрабатывается graceful."""
        monkeypatch.setattr(
            "codelab.server.http_server.ACPHttpServer",
            lambda **kwargs: MagicMock(),
        )
        monkeypatch.setattr(
            "codelab.server.storage.json_file.JsonFileStorage",
            lambda path: "storage",
        )
        monkeypatch.setattr(
            "codelab.server.config.AppConfig.from_env",
            classmethod(lambda cls: "config"),
        )
        monkeypatch.setattr("codelab.shared.logging.setup_logging", lambda **kwargs: None)
        monkeypatch.setattr(
            "codelab.cli.asyncio.run",
            lambda coro: (_ for _ in ()).throw(KeyboardInterrupt),
        )

        args = argparse.Namespace(
            host="127.0.0.1",
            port=cli_module.DEFAULT_PORT,
            stdio=False,
            no_web=False,
            trace_messages=False,
            require_auth=False,
            log_level=None,
            verbose=False,
        )

        run_serve(args)  # не должно поднимать исключение

    def test_keyboard_interrupt_stdio(self, monkeypatch: MonkeyPatch) -> None:
        """KeyboardInterrupt в stdio режиме обрабатывается graceful."""
        monkeypatch.setattr(
            "codelab.server.storage.json_file.JsonFileStorage",
            lambda path: "storage",
        )
        monkeypatch.setattr(
            "codelab.server.config.AppConfig.from_env",
            classmethod(lambda cls: "config"),
        )
        monkeypatch.setattr("codelab.shared.logging.setup_logging", lambda **kwargs: None)
        monkeypatch.setattr(
            "codelab.cli.asyncio.run",
            lambda coro: (_ for _ in ()).throw(KeyboardInterrupt),
        )

        args = argparse.Namespace(
            host="127.0.0.1",
            port=cli_module.DEFAULT_PORT,
            stdio=True,
            no_web=False,
            trace_messages=False,
            require_auth=False,
            log_level=None,
            verbose=False,
        )

        run_serve(args)  # не должно поднимать исключение


class TestRunTuiApp:
    """Тесты для _run_tui_app()."""

    def test_forwards_all_arguments(self, monkeypatch: MonkeyPatch) -> None:
        """Пробрасывает все аргументы в run_tui_app."""
        captured: dict[str, object] = {}
        monkeypatch.setattr(
            "codelab.client.tui.app.run_tui_app",
            lambda **kwargs: captured.update(kwargs),
        )

        _run_tui_app(
            host="127.0.0.1",
            port=8765,
            cwd="/tmp",
            transport_mode="stdio",
            stdio_command="python",
            stdio_args=["-m", "agent"],
            theme="light",
        )

        assert captured["host"] == "127.0.0.1"
        assert captured["port"] == 8765
        assert captured["cwd"] == "/tmp"
        assert captured["transport_mode"] == "stdio"
        assert captured["stdio_command"] == "python"
        assert captured["stdio_args"] == ["-m", "agent"]
        assert captured["theme"] == "light"

    def test_default_transport_mode(self, monkeypatch: MonkeyPatch) -> None:
        """По умолчанию используется websocket транспорт."""
        captured: dict[str, object] = {}
        monkeypatch.setattr(
            "codelab.client.tui.app.run_tui_app",
            lambda **kwargs: captured.update(kwargs),
        )

        _run_tui_app(host="127.0.0.1", port=8765)

        assert captured["transport_mode"] == "websocket"


class TestMain:
    """Тесты для main()."""

    def test_local_mode_by_default(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Без подкоманды запускается локальный режим."""
        monkeypatch.setattr(cli_module, "CODELAB_HOME", tmp_path)
        monkeypatch.setattr(sys, "argv", ["codelab"])
        run_local_mock = MagicMock()
        monkeypatch.setattr("codelab.cli.run_local", run_local_mock)
        monkeypatch.setattr("codelab.cli._configure_logging", lambda **kwargs: None)
        monkeypatch.setattr("codelab.cli.load_dotenv", lambda *args, **kwargs: None)

        main()

        run_local_mock.assert_called_once()

    def test_serve_mode(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Подкоманда serve вызывает run_serve."""
        monkeypatch.setattr(cli_module, "CODELAB_HOME", tmp_path)
        monkeypatch.setattr(sys, "argv", ["codelab", "serve", "--port", "4096"])
        run_serve_mock = MagicMock()
        monkeypatch.setattr("codelab.cli.run_serve", run_serve_mock)
        monkeypatch.setattr("codelab.cli._configure_logging", lambda **kwargs: None)
        monkeypatch.setattr("codelab.cli.load_dotenv", lambda *args, **kwargs: None)

        main()

        run_serve_mock.assert_called_once()
        args = run_serve_mock.call_args[0][0]
        assert args.port == 4096
        assert args.command == "serve"

    def test_connect_mode(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Подкоманда connect вызывает run_connect."""
        monkeypatch.setattr(cli_module, "CODELAB_HOME", tmp_path)
        monkeypatch.setattr(sys, "argv", ["codelab", "connect", "--host", "remote"])
        run_connect_mock = MagicMock()
        monkeypatch.setattr("codelab.cli.run_connect", run_connect_mock)
        monkeypatch.setattr("codelab.cli._configure_logging", lambda **kwargs: None)
        monkeypatch.setattr("codelab.cli.load_dotenv", lambda *args, **kwargs: None)

        main()

        run_connect_mock.assert_called_once()
        args = run_connect_mock.call_args[0][0]
        assert args.host == "remote"
        assert args.command == "connect"

    def test_keyboard_interrupt_exits_gracefully(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Ctrl+C приводит к выходу с кодом 0."""
        monkeypatch.setattr(cli_module, "CODELAB_HOME", tmp_path)
        monkeypatch.setattr(sys, "argv", ["codelab"])
        monkeypatch.setattr("codelab.cli.run_local", MagicMock(side_effect=KeyboardInterrupt))
        monkeypatch.setattr("codelab.cli._configure_logging", lambda **kwargs: None)
        monkeypatch.setattr("codelab.cli.load_dotenv", lambda *args, **kwargs: None)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0

    def test_stdio_serve_sets_logging_before_ensure_home(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """В stdio режиме логирование настраивается до ensure_home_directory."""
        monkeypatch.setattr(cli_module, "CODELAB_HOME", tmp_path)
        monkeypatch.setattr(sys, "argv", ["codelab", "serve", "--stdio"])
        monkeypatch.setattr("codelab.cli.run_serve", MagicMock())
        monkeypatch.setattr("codelab.cli._configure_logging", lambda **kwargs: None)
        monkeypatch.setattr("codelab.cli.load_dotenv", lambda *args, **kwargs: None)

        setup_calls: list[dict[str, object]] = []
        monkeypatch.setattr(
            "codelab.shared.logging.setup_logging",
            lambda **kwargs: setup_calls.append(kwargs),
        )
        ensure_calls: list[None] = []
        original_ensure = ensure_home_directory
        monkeypatch.setattr(
            "codelab.cli.ensure_home_directory",
            lambda: ensure_calls.append(None) or original_ensure(),
        )

        main()

        assert setup_calls[0]["stderr_only"] is True
        assert len(ensure_calls) == 1

    def test_loads_home_env_first(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Глобальный .env загружается первым, локальный — с override."""
        monkeypatch.setattr(cli_module, "CODELAB_HOME", tmp_path)
        monkeypatch.setattr(sys, "argv", ["codelab"])
        monkeypatch.setattr("codelab.cli.run_local", MagicMock())
        monkeypatch.setattr("codelab.cli._configure_logging", lambda **kwargs: None)
        monkeypatch.setattr("codelab.cli.ensure_home_directory", lambda: None)

        home_env = tmp_path / "config" / ".env"
        home_env.parent.mkdir(parents=True)
        home_env.write_text("KEY=global", encoding="utf-8")

        calls: list[tuple[object, dict[str, object]]] = []
        monkeypatch.setattr(
            "codelab.cli.load_dotenv",
            lambda *args, **kwargs: calls.append((args[0] if args else None, kwargs)),
        )

        main()

        assert calls[0] == (home_env, {})
        assert calls[1] == (None, {"override": True})

    def test_verbose_configures_logging(
        self,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Флаг -v передаётся в _configure_logging."""
        monkeypatch.setattr(cli_module, "CODELAB_HOME", tmp_path)
        monkeypatch.setattr(sys, "argv", ["codelab", "-v"])
        monkeypatch.setattr("codelab.cli.run_local", MagicMock())
        monkeypatch.setattr("codelab.cli.load_dotenv", lambda *args, **kwargs: None)

        logging_calls: list[dict[str, object]] = []
        monkeypatch.setattr(
            "codelab.cli._configure_logging",
            lambda **kwargs: logging_calls.append(kwargs),
        )

        main()

        assert logging_calls[0]["verbose"] is True


class TestModuleEntrypoint:
    """Тесты для точки входа при запуске модуля."""

    def test_main_called_on_import_guard(self) -> None:
        """main() вызывается только при __name__ == '__main__'."""
        with patch.object(cli_module, "main") as main_mock:
            # Имитируем исполнение блока if __name__ == "__main__":
            main_mock.assert_not_called()
            cli_module.main()
            main_mock.assert_called_once()
