"""Точка входа для запуска TUI клиента как модуля."""

from __future__ import annotations

import argparse

from codelab.shared.logging import setup_logging

from .app import run_tui_app


def main() -> None:
    """Запускает TUI приложение с параметрами хоста, порта, рабочей директории и логирования."""

    parser = argparse.ArgumentParser(prog="codelab connect")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", default=None, type=int)
    parser.add_argument(
        "-cwd",
        "--cwd",
        default=None,
        help="Путь к проекту (default: текущая рабочая директория)",
    )
    parser.add_argument(
        "--history-dir",
        default=None,
        help=(
            "Путь к локальной истории чата "
            "(default: ACP_CLIENT_HISTORY_DIR или ~/.codelab/history)"
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Уровень логирования (default: INFO)",
    )
    parser.add_argument(
        "--log-json",
        action="store_true",
        help="Использовать JSON формат для логов",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Путь к файлу логов. 'default' для ~/.codelab/logs/codelab-client.log",
    )
    args = parser.parse_args()

    # Инициализировать логирование с сохранением в ~/.codelab/logs/codelab-client.log по умолчанию
    setup_logging(
        level=args.log_level,
        json_format=args.log_json,
        log_file=args.log_file or "default",
    )

    run_tui_app(
        host=args.host,
        port=args.port,
        cwd=args.cwd,
        history_dir=args.history_dir,
    )


if __name__ == "__main__":
    main()
