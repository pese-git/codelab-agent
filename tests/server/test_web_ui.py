"""Тесты покрытия для WebUIManager."""

from __future__ import annotations

import os
import signal
import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from codelab.shared.web_ui import WebUIManager

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def isolated_codelab_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Изолировать CODELAB_HOME: запуск Web UI открывает файл лога подпроцесса."""
    monkeypatch.setenv("CODELAB_HOME", str(tmp_path))
    return tmp_path


class TestWebUIManagerInit:
    """Тесты инициализации WebUIManager."""

    def test_init_stores_host_and_port(self) -> None:
        """Инициализация сохраняет host и port."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        assert manager.host == "127.0.0.1"
        assert manager.port == 8080

    def test_init_process_is_none(self) -> None:
        """Инициализация устанавливает _process в None."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        assert manager._process is None

    def test_init_web_ui_url_is_none(self) -> None:
        """Инициализация устанавливает _web_ui_url в None."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        assert manager._web_ui_url is None


class TestIsRunning:
    """Тесты свойства is_running."""

    def test_is_running_false_when_no_process(self) -> None:
        """is_running=False когда процесс не запущен."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        assert manager.is_running is False

    def test_is_running_false_when_process_dead(self) -> None:
        """is_running=False когда процесс мёртв."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.poll.return_value = 1  # мёртв
        manager._process = process
        manager._web_ui_url = "http://127.0.0.1:9080/"

        assert manager.is_running is False

    def test_is_running_true_when_process_alive(self) -> None:
        """is_running=True когда процесс жив и URL установлен."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.poll.return_value = None  # жив
        manager._process = process
        manager._web_ui_url = "http://127.0.0.1:9080/"

        assert manager.is_running is True


class TestWebUiUrl:
    """Тесты свойства web_ui_url."""

    def test_web_ui_url_none_when_not_running(self) -> None:
        """web_ui_url=None когда менеджер не запущен."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        assert manager.web_ui_url is None

    def test_web_ui_url_returns_url_when_running(self) -> None:
        """web_ui_url возвращает URL когда менеджер запущен."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.poll.return_value = None
        manager._process = process
        manager._web_ui_url = "http://127.0.0.1:9080/"

        assert manager.web_ui_url == "http://127.0.0.1:9080/"


class TestStopSubprocess:
    """Тесты остановки subprocess."""

    def test_no_process_is_noop(self) -> None:
        """Если процесса нет, метод не делает ничего и не падает."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        manager.stop_subprocess()

        assert manager._process is None

    def test_terminate_success(self) -> None:
        """При успешной остановке группы и wait процесс сбрасывается в None."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.pid = 12345
        process.wait = MagicMock()
        manager._process = process

        with patch("os.getpgid", return_value=12345) as getpgid:
            with patch("os.killpg") as killpg:
                manager.stop_subprocess()

        getpgid.assert_called_once_with(12345)
        killpg.assert_called_once_with(12345, signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=5)
        assert manager._process is None

    def test_terminates_whole_process_group_not_only_child(self) -> None:
        """Сигнал идёт группе: textual-serve порождает в ней своих детей (P2-53)."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.pid = 4242
        manager._process = process

        with patch("os.getpgid", return_value=4242):
            with patch("os.killpg") as killpg:
                manager.stop_subprocess()

        killpg.assert_called_once_with(4242, signal.SIGTERM)
        process.terminate.assert_not_called()

    def test_falls_back_to_terminate_when_killpg_fails(self) -> None:
        """Если группу погасить нельзя, остаётся обычный terminate по pid."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.pid = 777
        manager._process = process

        with patch("os.getpgid", side_effect=OSError("no such process group")):
            manager.stop_subprocess()

        process.terminate.assert_called_once()
        assert manager._process is None

    def test_terminate_timeout_then_kill(self) -> None:
        """При TimeoutExpired должен вызываться kill, процесс обнулён."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.pid = 12345
        process.wait = MagicMock(
            side_effect=subprocess.TimeoutExpired(cmd="cmd", timeout=5),
        )
        process.kill = MagicMock()
        manager._process = process

        with patch("os.getpgid", return_value=12345):
            with patch("os.killpg"):
                manager.stop_subprocess()

        process.wait.assert_called_once_with(timeout=5)
        process.kill.assert_called_once()
        assert manager._process is None

    def test_kill_also_fails_still_clears_process(self) -> None:
        """Даже если и terminate, и kill падают, процесс сбрасывается в None."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.pid = 999
        process.terminate = MagicMock(side_effect=ProcessLookupError("no process"))
        process.kill = MagicMock(side_effect=OSError("kill failed"))
        manager._process = process

        with patch("os.getpgid", side_effect=OSError("gone")):
            manager.stop_subprocess()

        assert manager._process is None


class TestGetResponse:
    """Тесты метода get_response."""

    async def test_subprocess_running_returns_iframe_html(self) -> None:
        """Запущенный subprocess возвращает HTML-страницу с iframe."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.poll.return_value = None
        manager._process = process
        manager._web_ui_url = "http://127.0.0.1:9080/"

        response = manager.get_response()

        assert response.content_type == "text/html"
        assert "iframe" in response.text
        assert "http://127.0.0.1:9080/" in response.text

    async def test_subprocess_dead_falls_through_to_manual_start(self) -> None:
        """Мёртвый subprocess fallback к manual start HTML."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.poll.return_value = 1  # мёртв
        manager._process = process
        manager._web_ui_url = "http://127.0.0.1:9080/"

        with patch("codelab.server.web_app.is_web_ui_available", return_value=True):
            response = manager.get_response()

        assert response.content_type == "text/html"
        assert "textual-web" in response.text

    async def test_no_subprocess_but_available_returns_manual_start_html(self) -> None:
        """Без subprocess, но textual-web доступен — manual start HTML."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        with patch("codelab.server.web_app.is_web_ui_available", return_value=True):
            response = manager.get_response()

        assert response.content_type == "text/html"
        assert "textual-web" in response.text

    async def test_unavailable_returns_fallback_html(self) -> None:
        """Textual-web не доступен — fallback HTML."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        with patch("codelab.server.web_app.is_web_ui_available", return_value=False):
            response = manager.get_response()

        assert response.content_type == "text/html"
        assert "pip install" in response.text or "codelab[web]" in response.text


class TestValidateHost:
    """Тесты метода _validate_host."""

    def test_valid_ip_returns_unchanged(self) -> None:
        """Валидный IP возвращается без изменений."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        result = manager._validate_host("192.168.1.1")

        assert result == "192.168.1.1"

    def test_valid_hostname_returns_unchanged(self) -> None:
        """Валидный hostname возвращается без изменений."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        result = manager._validate_host("example.com")

        assert result == "example.com"

    def test_invalid_host_raises_value_error(self) -> None:
        """Невалидный host вызывает ValueError."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        with pytest.raises(ValueError, match="Invalid host"):
            manager._validate_host("invalid host with spaces")


class TestStartSubprocess:
    """Тесты метода start_subprocess."""

    def test_unavailable_returns_false(self) -> None:
        """Если textual-web не доступен, возвращает False."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        with patch("codelab.server.web_app.is_web_ui_available", return_value=False):
            result = manager.start_subprocess()

        assert result is False
        assert manager._process is None

    def test_success_starts_process(self) -> None:
        """При успехе запускает процесс и устанавливает URL."""
        manager = WebUIManager(host="127.0.0.1", port=8080)
        mock_process = MagicMock()
        mock_process.pid = 12345

        with patch("codelab.server.web_app.is_web_ui_available", return_value=True):
            with patch("subprocess.Popen", return_value=mock_process):
                result = manager.start_subprocess()

        assert result is True
        assert manager._process is mock_process
        assert manager._web_ui_url == "http://127.0.0.1:9080/"

    def test_passes_parent_pid_to_child(self) -> None:
        """Ребёнок получает pid родителя — иначе он не узнает о его смерти (P2-53)."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        with patch("codelab.server.web_app.is_web_ui_available", return_value=True):
            with patch("subprocess.Popen", return_value=MagicMock()) as popen:
                manager.start_subprocess()

        child_env = popen.call_args.kwargs["env"]
        assert child_env["CODELAB_PARENT_PID"] == str(os.getpid())

    def test_child_output_goes_to_log_not_devnull(self, isolated_codelab_home: Path) -> None:
        """У подпроцесса есть канал наблюдаемости: вывод пишется в файл лога."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        with patch("codelab.server.web_app.is_web_ui_available", return_value=True):
            with patch("subprocess.Popen", return_value=MagicMock()) as popen:
                manager.start_subprocess()

        assert popen.call_args.kwargs["stdout"] is not subprocess.DEVNULL
        assert popen.call_args.kwargs["stderr"] == subprocess.STDOUT
        assert (isolated_codelab_home / "logs" / f"web_ui-{os.getpid()}.log").exists()

    def test_unwritable_log_falls_back_to_devnull(self) -> None:
        """Недоступный файл лога не мешает запуску Web UI."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        with patch("codelab.server.web_app.is_web_ui_available", return_value=True):
            with patch(
                "codelab.shared.web_ui.get_logs_dir",
                side_effect=OSError("read-only fs"),
            ):
                with patch("subprocess.Popen", return_value=MagicMock()) as popen:
                    result = manager.start_subprocess()

        assert result is True
        assert popen.call_args.kwargs["stdout"] is subprocess.DEVNULL
        assert popen.call_args.kwargs["stderr"] is subprocess.DEVNULL

    def test_exception_returns_false(self) -> None:
        """При исключении возвращает False."""
        manager = WebUIManager(host="127.0.0.1", port=8080)

        with patch("codelab.server.web_app.is_web_ui_available", return_value=True):
            with patch("subprocess.Popen", side_effect=OSError("spawn failed")):
                result = manager.start_subprocess()

        assert result is False
        assert manager._process is None
