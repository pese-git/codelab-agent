"""Точка входа для запуска textual-serve.

Читает параметры подключения из переменных окружения,
установленных родительским процессом.
Использование: python -m codelab.client.tui.serve_entry
"""

from __future__ import annotations

import os
import sys
import threading
import time

import structlog

logger = structlog.get_logger(__name__)

PARENT_POLL_SECONDS = 5.0


def _parent_alive(parent_pid: int) -> bool:
    """Проверить, жив ли ещё родительский процесс.

    Проверяются оба признака: смена ppid (нас репарентировали к init, потому что
    родитель умер) и доступность самого pid — второе закрывает случай, когда
    родитель стал зомби и ppid ещё указывает на него.
    """
    if os.getppid() != parent_pid:
        return False
    try:
        os.kill(parent_pid, 0)
    except OSError:
        return False
    return True


def _watch_parent(parent_pid: int, poll_seconds: float = PARENT_POLL_SECONDS) -> None:
    """Завершить процесс, когда родитель исчез, не успев нас остановить.

    Мы живём в отдельной сессии, чтобы Ctrl-C в терминале не убивал Web UI,
    поэтому смерть родителя нас не задевает: `SIGKILL` родителю или его падение
    оставляли нас сиротой навсегда (P2-53). `textual_serve.Server.serve()`
    блокирует главный поток и не отдаёт точки останова, поэтому выход жёсткий —
    иначе сторож не смог бы прервать сервер.
    """
    while True:
        time.sleep(poll_seconds)
        if not _parent_alive(parent_pid):
            logger.warning(
                "web_ui_parent_gone_exiting",
                parent_pid=parent_pid,
                pid=os.getpid(),
            )
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)


def _start_parent_watchdog() -> None:
    """Поднять сторожа за родителем, если тот передал свой pid."""
    raw_pid = os.environ.get("CODELAB_PARENT_PID")
    if not raw_pid:
        return

    try:
        parent_pid = int(raw_pid)
    except ValueError:
        logger.warning("web_ui_parent_pid_invalid", value=raw_pid)
        return

    threading.Thread(
        target=_watch_parent,
        args=(parent_pid,),
        name="web-ui-parent-watchdog",
        daemon=True,
    ).start()


def main() -> None:
    """Запускает textual-serve сервер для Web UI."""
    ws_host = os.environ.get("CODELAB_WS_HOST", "127.0.0.1")
    ws_port = os.environ.get("CODELAB_WS_PORT", "8765")
    web_port = int(os.environ.get("CODELAB_WEB_UI_PORT", "9765"))
    web_host = os.environ.get("CODELAB_WEB_UI_HOST", "127.0.0.1")

    try:
        from textual_serve.server import Server
    except ImportError:
        print("textual-serve not installed. Run: pip install 'codelab[web]'", file=sys.stderr)
        sys.exit(1)

    _start_parent_watchdog()

    server = Server(
        command=f"{sys.executable} -m codelab.client.tui --host {ws_host} --port {ws_port}",
        host=web_host,
        port=web_port,
        title="CodeLab TUI",
    )
    server.serve()


if __name__ == "__main__":
    main()
