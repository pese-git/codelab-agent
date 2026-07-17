"""Пакет AgentLoop — унифицированный цикл итераций LLM tool-calling.

Публичный API сохранён через re-export: импорт
`from ...pipeline.stages.agent_loop import AgentLoop` продолжает работать
после разбиения модуля на пакет (P1-4).
"""

from __future__ import annotations

from codelab.server.protocol.handlers.pipeline.stages.agent_loop.loop import (
    AgentLoop,
    AgentLoopResult,
    StopReason,
    ToolProcessingResult,
    ToolResult,
)

__all__ = [
    "AgentLoop",
    "AgentLoopResult",
    "StopReason",
    "ToolProcessingResult",
    "ToolResult",
]
