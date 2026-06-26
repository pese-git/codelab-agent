"""Decorator для автоматического извлечения структуры проекта.

Перехватывает terminal/create для сохранения маппинга terminal_id → command,
затем перехватывает terminal/wait_for_exit для парсинга вывода и сохранения
структуры проекта в session.config_values["project_structure"].

Архитектура terminal в ACP:
1. terminal/create → создаёт терминал, возвращает terminal_id в metadata
2. terminal/wait_for_exit → ожидает завершения, возвращает output
3. terminal/release → освобождает ресурсы

Decorator перехватывает create и wait_for_exit, связывая их через terminal_id.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.tools.base import ToolExecutionResult

from .base import ToolExecutorDecorator, ToolExecutorProtocol

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()

IGNORE_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "node_modules",
    ".idea", ".vscode", "build", "dist", ".dart_tool",
    ".fvm", "android", "ios", "macos", "linux", "windows", "web",
    ".DS_Store", ".gradle", ".codelab",
}

STRUCTURE_COMMANDS = {"find", "ls"}


class ProjectStructureDecorator(ToolExecutorDecorator):
    """Автоматически извлекает структуру проекта из terminal output.

    Архитектура:
    1. terminal/create → сохраняет terminal_id → command в маппинг
    2. terminal/wait_for_exit → читает output, парсит, сохраняет в session

    Example:
        >>> executor = ProjectStructureDecorator(base_executor)
        >>> # terminal/create: сохраняет terminal_id → "find . -type f"
        >>> # terminal/wait_for_exit: парсит output → session.config_values
    """

    def __init__(
        self,
        wrapped: ToolExecutorProtocol,
    ) -> None:
        super().__init__(wrapped)
        self._terminal_commands: dict[str, str] = {}
        self._lock = threading.Lock()

    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить инструмент и извлечь структуру проекта если применимо."""
        result = await self._wrapped.execute(session, arguments)

        if not result.success:
            return result

        operation = arguments.get("operation", "")

        if operation == "create":
            self._handle_terminal_create(result, arguments)
        elif operation == "wait_for_exit":
            self._handle_terminal_wait(session, result, arguments)

        return result

    def _handle_terminal_create(
        self,
        result: ToolExecutionResult,
        arguments: dict[str, Any],
    ) -> None:
        """Сохранить маппинг terminal_id → command."""
        terminal_id = ""
        if result.metadata:
            terminal_id = result.metadata.get("terminal_id", "")
        if not terminal_id and result.raw_output:
            terminal_id = result.raw_output.get("terminal_id", "")
        if not terminal_id:
            return

        command_str = arguments.get("command", "")
        base_command = command_str.split()[0] if command_str else ""

        if base_command not in STRUCTURE_COMMANDS:
            return

        with self._lock:
            self._terminal_commands[terminal_id] = command_str

        logger.debug(
            "project_structure.terminal_tracked",
            terminal_id=terminal_id,
            command=command_str,
            base_command=base_command,
        )

    def _handle_terminal_wait(
        self,
        session: SessionState,
        result: ToolExecutionResult,
        arguments: dict[str, Any],
    ) -> None:
        """Парсить output и сохранить структуру проекта."""
        terminal_id = arguments.get("terminal_id", "")
        if not terminal_id:
            return

        with self._lock:
            command_str = self._terminal_commands.pop(terminal_id, "")

        if not command_str:
            return

        output = result.output or ""
        if not output.strip():
            return

        base_command = command_str.split()[0] if command_str else ""
        files = self._parse_output(base_command, command_str, output)
        if not files:
            return

        filtered = self._filter_paths(files)
        if not filtered:
            return

        session.config_values["project_structure"] = json.dumps(filtered)

        logger.info(
            "project_structure.auto_saved",
            session_id=session.session_id,
            terminal_id=terminal_id,
            command=command_str,
            total_files=len(files),
            filtered_files=len(filtered),
        )

    def _parse_output(
        self,
        base_command: str,
        full_command: str,
        output: str,
    ) -> list[str]:
        """Парсить вывод терминала в список путей."""
        if base_command == "find":
            return self._parse_find_output(output)
        if base_command == "ls":
            return self._parse_ls_output(full_command, output)
        return []

    @staticmethod
    def _parse_find_output(output: str) -> list[str]:
        """Парсить вывод find команды."""
        paths = []
        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("find:"):
                continue
            if line.startswith("./"):
                line = line[2:]
            if line:
                paths.append(line)
        return paths

    @staticmethod
    def _parse_ls_output(full_command: str, output: str) -> list[str]:
        """Парсить вывод ls команды."""
        parts = full_command.split()
        has_l_flag = any("l" in p.lstrip("-") for p in parts if p.startswith("-"))

        paths: list[str] = []
        current_dir = ""

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.endswith(":") and not line.startswith("total"):
                current_dir = line[:-1]
                if current_dir.startswith("./"):
                    current_dir = current_dir[2:]
                continue

            if line.startswith("total "):
                continue

            if has_l_flag:
                line_parts = line.split()
                if len(line_parts) < 9:
                    continue
                name = " ".join(line_parts[8:])
            else:
                name = line

            if name in (".", ".."):
                continue

            full_path = f"{current_dir}/{name}" if current_dir else name

            if not name.startswith("."):
                paths.append(full_path)

        return paths

    @staticmethod
    def _filter_paths(paths: list[str]) -> list[str]:
        """Отфильтровать мусорные папки и файлы."""
        filtered = []
        for path in paths:
            normalized = path.replace("\\", "/").strip()

            if not normalized or normalized in (".", "./"):
                continue

            if normalized.startswith("./"):
                normalized = normalized[2:]

            if not normalized:
                continue

            dir_parts = normalized.split("/")

            if any(part in IGNORE_DIRS for part in dir_parts):
                continue

            filtered.append(normalized)

        return filtered
