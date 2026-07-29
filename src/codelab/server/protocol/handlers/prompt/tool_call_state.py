"""Мутации состояния tool call в сессии (кандидат на переезд в домен).

Создание записи и смена статуса с проверкой матрицы переходов. Раньше жило в
`tool_calls.py` вместе с ACP-рендером и жизненным циклом turn'а; расщеплено,
потому что в фазе D эти три дела расходятся: рендер остаётся на wire, turn имеет
свою точку сцепления (`TurnLifecycleManager`), а этот модуль целиком становится
операциями доменного `ToolCallRegistry` (фаза C ADR-006).
"""

from __future__ import annotations

from typing import Any

from ...state import SessionState, ToolCallState


def create_tool_call(session: SessionState, *, title: str, kind: str) -> str:
    """Создает запись нового tool call в состоянии сессии.

    Пример использования:
        tool_call_id = create_tool_call(state, title="Demo", kind="other")
    """

    # Локально монотонный ID делает тесты предсказуемыми и читабельными.
    session.tool_call_counter += 1
    tool_call_id = f"call_{session.tool_call_counter:03d}"
    session.tool_calls[tool_call_id] = ToolCallState(
        tool_call_id=tool_call_id,
        title=title,
        kind=kind,
        status="pending",
    )
    return tool_call_id


def update_tool_call_status(
    session: SessionState,
    tool_call_id: str,
    status: str,
    *,
    content: list[dict[str, Any]] | None = None,
) -> None:
    """Обновляет статус tool call с проверкой допустимых переходов.

    Пример использования:
        update_tool_call_status(state, "call_001", "in_progress")
    """

    state = session.tool_calls.get(tool_call_id)
    if state is None:
        return

    # Явная матрица переходов защищает от нелегальных смен статуса.
    allowed_transitions: dict[str, set[str]] = {
        "pending": {"in_progress", "cancelled", "failed"},
        "in_progress": {"completed", "cancelled", "failed"},
        "completed": set(),
        "cancelled": set(),
        "failed": set(),
    }
    next_states = allowed_transitions.get(state.status, set())
    if status not in next_states and status != state.status:
        return

    state.status = status
    if content is not None:
        state.content = content
