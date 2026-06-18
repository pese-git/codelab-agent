"""Дополнительные тесты для повышения покрытия codelab.server.cli."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from codelab.server.cli import _run_stdio_server, run_server


@pytest.fixture
def cli_mocks() -> Iterator[SimpleNamespace]:
    """Фикстура с моками внешних зависимостей run_server."""
    logger = MagicMock()
    config = MagicMock()
    config.storage.session_cache_size = 100

    server_mock = MagicMock()
    server_mock.run = AsyncMock(return_value=None)

    acp_http_class = MagicMock(return_value=server_mock)
    cached_storage = MagicMock()
    timeout_config = MagicMock()

    with (
        patch("codelab.server.cli.load_dotenv") as load_dotenv_mock,
        patch("codelab.server.cli.setup_logging", return_value=logger) as setup_logging_mock,
        patch("codelab.server.cli.structlog.get_logger", return_value=logger) as get_logger_mock,
        patch("codelab.server.cli.AppConfig.load", return_value=config) as app_config_load_mock,
        patch("codelab.server.cli.ACPHttpServer", acp_http_class),
        patch("codelab.server.cli.CachedSessionStorage", cached_storage),
        patch(
            "codelab.server.toml_config.pydantic_config.TimeoutConfig",
            timeout_config,
        ),
    ):
        yield SimpleNamespace(
            logger=logger,
            config=config,
            acp_http_class=acp_http_class,
            server_mock=server_mock,
            cached_storage=cached_storage,
            timeout_config=timeout_config,
            load_dotenv=load_dotenv_mock,
            setup_logging=setup_logging_mock,
            get_logger=get_logger_mock,
            app_config_load=app_config_load_mock,
        )


class TestRunServerWebSocket:
    """Тесты для WebSocket-режима run_server."""

    def test_run_server_default_starts_http_server(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить запуск WebSocket-сервера с аргументами по умолчанию."""
        test_args = ["codelab"]
        with patch.object(sys, "argv", test_args):
            run_server()

        cli_mocks.setup_logging.assert_called_once_with(
            level="INFO",
            json_format=False,
            log_file=None,
            stderr_only=False,
        )
        cli_mocks.app_config_load.assert_called_once_with(toml_path=None)
        cli_mocks.acp_http_class.assert_called_once_with(
            host="127.0.0.1",
            port=8765,
            require_auth=False,
            auth_api_key=None,
            storage=cli_mocks.cached_storage.return_value,
            config=cli_mocks.config,
            enable_web=True,
            trace_messages=False,
        )
        cli_mocks.server_mock.run.assert_awaited_once()

    def test_run_server_host_and_port(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить передачу --host и --port в HTTP-сервер."""
        test_args = ["codelab", "--host", "0.0.0.0", "--port", "9999"]
        with patch.object(sys, "argv", test_args):
            run_server()

        cli_mocks.acp_http_class.assert_called_once_with(
            host="0.0.0.0",
            port=9999,
            require_auth=False,
            auth_api_key=None,
            storage=ANY,
            config=cli_mocks.config,
            enable_web=True,
            trace_messages=False,
        )

    def test_run_server_log_options(self, cli_mocks: SimpleNamespace, tmp_path: Path) -> None:
        """Проверить обработку --log-level, --log-json и --log-file."""
        custom_log = tmp_path / "server.log"
        test_args = [
            "codelab",
            "--log-level",
            "DEBUG",
            "--log-json",
            "--log-file",
            str(custom_log),
        ]
        with patch.object(sys, "argv", test_args):
            run_server()

        cli_mocks.setup_logging.assert_called_once_with(
            level="DEBUG",
            json_format=True,
            log_file=str(custom_log),
            stderr_only=False,
        )

    def test_run_server_default_log_file(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить передачу специального значения 'default' для --log-file."""
        test_args = ["codelab", "--log-file", "default"]
        with patch.object(sys, "argv", test_args):
            run_server()

        cli_mocks.setup_logging.assert_called_once_with(
            level="INFO",
            json_format=False,
            log_file="default",
            stderr_only=False,
        )

    def test_run_server_trace_messages(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить передачу флага --trace-messages в HTTP-сервер."""
        test_args = ["codelab", "--trace-messages"]
        with patch.object(sys, "argv", test_args):
            run_server()

        cli_mocks.acp_http_class.assert_called_once_with(
            host="127.0.0.1",
            port=8765,
            require_auth=False,
            auth_api_key=None,
            storage=ANY,
            config=cli_mocks.config,
            enable_web=True,
            trace_messages=True,
        )

    def test_run_server_llm_overrides(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить переопределение параметров LLM из командной строки."""
        test_args = [
            "codelab",
            "--llm-provider",
            "openai",
            "--llm-model",
            "gpt-4",
            "--llm-api-key",
            "secret",
            "--llm-base-url",
            "http://localhost",
            "--llm-temperature",
            "0.5",
            "--llm-max-tokens",
            "1024",
            "--system-prompt",
            "custom prompt",
        ]
        with patch.object(sys, "argv", test_args):
            run_server()

        assert cli_mocks.config.llm.provider == "openai"
        assert cli_mocks.config.llm.model == "gpt-4"
        assert cli_mocks.config.llm.api_key == "secret"
        assert cli_mocks.config.llm.base_url == "http://localhost"
        assert cli_mocks.config.llm.temperature == 0.5
        assert cli_mocks.config.llm.max_tokens == 1024
        assert cli_mocks.config.agent.system_prompt == "custom prompt"
        cli_mocks.logger.debug.assert_any_call(
            "configuration overridden",
            overrides=ANY,
        )

    def test_run_server_llm_timeout_overrides(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить переопределение таймаутов LLM из CLI."""
        test_args = [
            "codelab",
            "--llm-timeout-connect",
            "5.0",
            "--llm-timeout-read",
            "60.0",
            "--llm-timeout-write",
            "10.0",
            "--llm-timeout-pool",
            "15.0",
        ]
        with patch.object(sys, "argv", test_args):
            run_server()

        cli_mocks.timeout_config.assert_called_once_with(
            connect=5.0,
            read=60.0,
            write=10.0,
            pool=15.0,
        )
        assert cli_mocks.config.llm.timeout == cli_mocks.timeout_config.return_value

    def test_run_server_fallback_args(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить логирование fallback аргументов из CLI."""
        test_args = [
            "codelab",
            "--fallback-enabled",
            "--fallback-strategy",
            "sequential",
            "--fallback-order",
            "openai,anthropic",
        ]
        with patch.object(sys, "argv", test_args):
            run_server()

        cli_mocks.logger.debug.assert_any_call("fallback enabled via CLI")
        cli_mocks.logger.debug.assert_any_call(
            "fallback strategy set via CLI",
            strategy="sequential",
        )
        cli_mocks.logger.debug.assert_any_call(
            "fallback order set via CLI",
            order=["openai", "anthropic"],
        )

    def test_run_server_json_storage(self, cli_mocks: SimpleNamespace, tmp_path: Path) -> None:
        """Проверить инициализацию JSON файлового хранилища через CLI."""
        sessions_dir = tmp_path / "sessions"
        test_args = ["codelab", "--storage", f"json:{sessions_dir}"]
        with patch.object(sys, "argv", test_args):
            run_server()

        cli_mocks.cached_storage.assert_called_once_with(
            backend=ANY,
            max_size=100,
        )
        cli_mocks.logger.info.assert_any_call(
            "storage_backend_initialized",
            storage_type="JsonFileStorage",
            storage_target=ANY,
            session_cache_size=100,
        )

    def test_run_server_auth_api_key_from_cli(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить использование API ключа аутентификации из CLI."""
        test_args = ["codelab", "--require-auth", "--auth-api-key", "key123"]
        with patch.object(sys, "argv", test_args):
            run_server()

        cli_mocks.acp_http_class.assert_called_once_with(
            host="127.0.0.1",
            port=8765,
            require_auth=True,
            auth_api_key="key123",
            storage=ANY,
            config=cli_mocks.config,
            enable_web=True,
            trace_messages=False,
        )

    def test_run_server_auth_api_key_from_env(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить загрузку API ключа аутентификации из переменных окружения."""
        test_args = ["codelab", "--require-auth"]
        with (
            patch.object(sys, "argv", test_args),
            patch("codelab.server.cli.os.getenv", return_value="env-key"),
        ):
            run_server()

        cli_mocks.acp_http_class.assert_called_once_with(
            host="127.0.0.1",
            port=8765,
            require_auth=True,
            auth_api_key="env-key",
            storage=ANY,
            config=cli_mocks.config,
            enable_web=True,
            trace_messages=False,
        )

    def test_run_server_require_auth_without_key_warns(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить предупреждение при --require-auth без API ключа."""
        test_args = ["codelab", "--require-auth"]
        with (
            patch.object(sys, "argv", test_args),
            patch("codelab.server.cli.os.getenv", return_value=None),
        ):
            run_server()

        cli_mocks.logger.warning.assert_called_once_with(
            "authentication required but no api key configured"
        )

    def test_run_server_keyboard_interrupt(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить корректную обработку KeyboardInterrupt."""
        cli_mocks.server_mock.run.side_effect = KeyboardInterrupt
        test_args = ["codelab"]
        with patch.object(sys, "argv", test_args):
            run_server()

        cli_mocks.logger.info.assert_any_call("server interrupted by user")

    def test_run_server_error_raises(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить проброс исключения при ошибке сервера."""
        cli_mocks.server_mock.run.side_effect = RuntimeError("boom")
        test_args = ["codelab"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(RuntimeError, match="boom"):
                run_server()

        cli_mocks.logger.error.assert_called_once_with(
            "server error",
            error="boom",
            exc_info=True,
        )


class TestRunServerStdio:
    """Тесты для stdio-режима run_server."""

    def test_run_server_stdio_mode(self, cli_mocks: SimpleNamespace) -> None:
        """Проверить передачу управления в stdio-сервер."""
        test_args = ["codelab", "--stdio"]
        with (
            patch.object(sys, "argv", test_args),
            patch(
                "codelab.server.transport.stdio_runner.run_stdio_server",
                new_callable=AsyncMock,
            ) as run_stdio_mock,
        ):
            run_server()

        cli_mocks.setup_logging.assert_called_once_with(
            level="INFO",
            json_format=False,
            log_file=None,
            stderr_only=True,
        )
        run_stdio_mock.assert_awaited_once_with(
            storage=cli_mocks.cached_storage.return_value,
            config=cli_mocks.config,
            require_auth=False,
            auth_api_key=None,
        )
        cli_mocks.acp_http_class.assert_not_called()


class TestRunStdioServerDirect:
    """Тесты для функции _run_stdio_server."""

    def test_run_stdio_server_starts(self) -> None:
        """Проверить запуск stdio-сервера с корректными параметрами."""
        logger = MagicMock()
        storage = MagicMock()
        config = MagicMock()
        with (
            patch("codelab.server.cli.structlog.get_logger", return_value=logger),
            patch(
                "codelab.server.transport.stdio_runner.run_stdio_server",
                new_callable=AsyncMock,
            ) as run_stdio_mock,
        ):
            _run_stdio_server(
                storage=storage,
                config=config,
                require_auth=True,
                auth_api_key="key",
                log_level="DEBUG",
                log_json=True,
                log_file="/tmp/log",
            )

        logger.info.assert_any_call(
            "stdio server starting",
            llm_provider=config.llm.provider,
            storage_type=type(storage).__name__,
        )
        run_stdio_mock.assert_awaited_once_with(
            storage=storage,
            config=config,
            require_auth=True,
            auth_api_key="key",
        )

    def test_run_stdio_server_keyboard_interrupt(self) -> None:
        """Проверить обработку KeyboardInterrupt в stdio режиме."""
        logger = MagicMock()
        with (
            patch("codelab.server.cli.structlog.get_logger", return_value=logger),
            patch(
                "codelab.server.transport.stdio_runner.run_stdio_server",
                side_effect=KeyboardInterrupt,
            ),
        ):
            _run_stdio_server(
                storage=MagicMock(),
                config=MagicMock(),
                require_auth=False,
                auth_api_key=None,
                log_level="INFO",
                log_json=False,
                log_file=None,
            )

        logger.info.assert_any_call("stdio server interrupted by user")

    def test_run_stdio_server_error_raises(self) -> None:
        """Проверить проброс исключения при ошибке stdio-сервера."""
        logger = MagicMock()
        with (
            patch("codelab.server.cli.structlog.get_logger", return_value=logger),
            patch(
                "codelab.server.transport.stdio_runner.run_stdio_server",
                side_effect=RuntimeError("boom"),
            ),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                _run_stdio_server(
                    storage=MagicMock(),
                    config=MagicMock(),
                    require_auth=False,
                    auth_api_key=None,
                    log_level="INFO",
                    log_json=False,
                    log_file=None,
                )

        logger.error.assert_called_once_with(
            "stdio server error",
            error="boom",
            exc_info=True,
        )
