"""FakeSessionView — реализация порта `SessionView` для тестов ядра.

Обычный dataclass без Pydantic и без `protocol.state.SessionDocument`: даёт ядру
read-поверхность (session_id, cwd, config_values, runtime_capabilities, history)
в тех же формах, что и живая сессия. Достаточно для юнит-тестов
`ExecutionEngine`, `HistoryBuilder`, `SystemPromptBuilder`, `ToolFilter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeCapabilities:
    """Реализация порта `ClientCapabilitiesView`."""

    fs_read: bool = False
    fs_write: bool = False
    terminal: bool = False


@dataclass
class FakeSessionView:
    """Реализация порта `SessionView` поверх простых структур."""

    session_id: str = "sess_fake"
    cwd: str = "/tmp/project"
    config_values: dict[str, str] = field(default_factory=dict)
    runtime_capabilities: FakeCapabilities | None = None
    history: list[Any] = field(default_factory=list)
