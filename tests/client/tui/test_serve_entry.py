"""Тесты для serve_entry.py — точки входа textual-serve."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from codelab.client.tui.serve_entry import (
    _parent_alive,
    _start_parent_watchdog,
    _watch_parent,
    main,
)


class TestServeEntry:
    """Тесты точки входа serve_entry."""

    @patch.dict(os.environ, {}, clear=True)
    @patch("textual_serve.server.Server")
    def test_uses_default_values_when_env_not_set(
        self,
        mock_server: MagicMock,
    ) -> None:
        """При отсутствии переменных окружения используются значения по умолчанию."""
        mock_server_instance = MagicMock()
        mock_server.return_value = mock_server_instance

        main()

        mock_server.assert_called_once()
        call_kwargs = mock_server.call_args[1]
        assert call_kwargs["host"] == "127.0.0.1"
        assert call_kwargs["port"] == 9765

    @patch.dict(
        os.environ,
        {
            "CODELAB_WS_HOST": "192.168.1.100",
            "CODELAB_WS_PORT": "9999",
            "CODELAB_WEB_UI_HOST": "0.0.0.0",
            "CODELAB_WEB_UI_PORT": "5000",
        },
    )
    @patch("textual_serve.server.Server")
    def test_reads_params_from_env(
        self,
        mock_server: MagicMock,
    ) -> None:
        """Параметры читаются из переменных окружения."""
        mock_server_instance = MagicMock()
        mock_server.return_value = mock_server_instance

        main()

        mock_server.assert_called_once()
        call_args = mock_server.call_args
        # Проверяем command (позиционный аргумент)
        command = call_args[1]["command"]
        assert "192.168.1.100" in command
        assert "9999" in command
        # Проверяем host и port (keyword аргументы)
        assert call_args[1]["host"] == "0.0.0.0"
        assert call_args[1]["port"] == 5000

    @patch.dict(os.environ, {}, clear=True)
    @patch("textual_serve.server.Server")
    def test_command_includes_ws_params(
        self,
        mock_server: MagicMock,
    ) -> None:
        """Command для textual-serve включает параметры подключения к WS."""
        mock_server_instance = MagicMock()
        mock_server.return_value = mock_server_instance

        main()

        call_kwargs = mock_server.call_args[1]
        command = call_kwargs["command"]
        assert "--host 127.0.0.1" in command
        assert "--port 8765" in command
        assert "codelab.client.tui" in command

    @patch.dict(os.environ, {}, clear=True)
    def test_exits_when_textual_serve_not_installed(
        self,
    ) -> None:
        """При отсутствии textual-serve программа завершается с ошибкой."""
        with (
            patch.dict(sys.modules, {"textual_serve.server": None}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


class TestParentAlive:
    """Тесты признака «родитель ещё жив»."""

    def test_alive_when_ppid_matches_and_pid_exists(self) -> None:
        """Совпадающий ppid и доступный pid означают живого родителя."""
        assert _parent_alive(os.getppid()) is True

    def test_dead_when_reparented(self) -> None:
        """Смена ppid означает, что родитель умер и нас репарентировали."""
        with patch("os.getppid", return_value=1):
            assert _parent_alive(4242) is False

    def test_dead_when_pid_unreachable(self) -> None:
        """Недоступный pid означает мёртвого родителя даже при совпавшем ppid."""
        with patch("os.getppid", return_value=4242):
            with patch("os.kill", side_effect=ProcessLookupError):
                assert _parent_alive(4242) is False


class TestWatchParent:
    """Тесты сторожа за родительским процессом."""

    def test_exits_process_when_parent_gone(self) -> None:
        """Исчезновение родителя завершает процесс: иначе он остаётся сиротой (P2-53)."""
        with patch("codelab.client.tui.serve_entry.time.sleep"):
            with patch(
                "codelab.client.tui.serve_entry._parent_alive",
                return_value=False,
            ):
                with patch("os._exit", side_effect=RuntimeError("exited")) as os_exit:
                    with pytest.raises(RuntimeError, match="exited"):
                        _watch_parent(4242, poll_seconds=0)

        os_exit.assert_called_once_with(0)

    def test_keeps_waiting_while_parent_alive(self) -> None:
        """Пока родитель жив, процесс не завершается."""
        alive_then_gone = [True, True, False]

        with patch("codelab.client.tui.serve_entry.time.sleep"):
            with patch(
                "codelab.client.tui.serve_entry._parent_alive",
                side_effect=alive_then_gone,
            ):
                with patch("os._exit", side_effect=RuntimeError("exited")):
                    with pytest.raises(RuntimeError, match="exited"):
                        _watch_parent(4242, poll_seconds=0)


class TestStartParentWatchdog:
    """Тесты подъёма сторожа."""

    @patch.dict(os.environ, {}, clear=True)
    def test_not_started_without_parent_pid(self) -> None:
        """Без pid родителя сторож не поднимается: ронять поток не на что."""
        with patch("threading.Thread") as thread:
            _start_parent_watchdog()

        thread.assert_not_called()

    @patch.dict(os.environ, {"CODELAB_PARENT_PID": "4242"})
    def test_starts_daemon_thread_with_parent_pid(self) -> None:
        """Сторож поднимается демоном, чтобы не держать выход процесса."""
        with patch("threading.Thread") as thread:
            _start_parent_watchdog()

        thread.assert_called_once()
        assert thread.call_args.kwargs["args"] == (4242,)
        assert thread.call_args.kwargs["daemon"] is True
        thread.return_value.start.assert_called_once()

    @patch.dict(os.environ, {"CODELAB_PARENT_PID": "не число"})
    def test_invalid_parent_pid_is_reported_not_raised(self) -> None:
        """Некорректный pid не роняет запуск Web UI."""
        with patch("threading.Thread") as thread:
            _start_parent_watchdog()

        thread.assert_not_called()
