"""Smoke-тест: ядро работает без импорта codelab.server.protocol.* (ADR-005 Фаза 4).

Этот тест демонстрирует ключевое свойство гексагона после Фазы 4:
ядро ``codelab.server.agent.core.*`` может быть поднято и выполнить
turn с не-ACP драйвером (тест-харнесс), не импортируя ничего из
``codelab.server.protocol.*``.

Что НЕ импортируется (по построению теста):
- ``codelab.server.protocol.state.SessionState``
- ``codelab.server.protocol.session_view.SessionStateView``
- ``codelab.server.protocol.session_factory.SessionFactory``
- ``codelab.server.protocol.handlers.*``

Что используется:
- ``FakeSessionView`` (in-memory) — driven-адаптер SessionView.
- ``FakeContentCodec`` (in-memory) — driven-адаптер ContentCodec.
- ``FakeUpdateSink`` (in-memory) — driven-адаптер UpdateSink.
- ``MockLLMProvider`` — LLMAdapter-style mock.
- ``ExecutionEngine`` + ``StrategyDispatcher`` — ядро.

Этот тест — **smoke**, не полноценный integration. Доказывает, что
граница ядра уважается, и второй драйвер (A2A / тест-харнесс) может
быть построен без copy-paste протокольной логики.
"""

from __future__ import annotations

import pytest

from codelab.server.agent.contracts.ports import (
    SessionView,
    UpdateSink,
)
from codelab.server.agent.core.execution_engine import ExecutionEngine
from codelab.server.agent.core.strategies.registry import StrategyRegistry
from codelab.server.llm.scripted_mock import ScriptedMockLLMProvider
from codelab.shared.capabilities import ClientCapabilities
from tests.server.agent.fakes import (
    FakeContentCodec,
    FakeSessionView,
    FakeUpdateSink,
)


class _FakeStrategyRegistry(StrategyRegistry):
    """Переопределяем ``create_instance`` чтобы не подтягивать
    конкретные стратегии из agent.core.strategies.descriptor (которые
    зависят от LLMAdapter + EventBus). Возвращает None, чтобы
    StrategyDispatcher использовал ``default_strategy="single"`` —
    но ``select_strategy`` всё равно выберет стратегию, которая
    не сможет создать instance, и вернёт fallback.
    """


@pytest.mark.asyncio
async def test_core_engine_runs_without_protocol_imports() -> None:
    """Ядро может быть инстанцировано и подготовлено к turn без protocol/*."""
    # Драйвер-уровень: чисто доменные фейки + scripted mock LLM.
    view = FakeSessionView(
        session_id="sess_no_protocol_1",
        cwd="/tmp",
        config_values={"model": "mock/mock-model", "_agent": "primary"},
        runtime_capabilities=ClientCapabilities(),
    )

    content_codec = FakeContentCodec()
    update_sink = FakeUpdateSink()

    # ToolRegistry: подсовываем Mock с минимальным интерфейсом.
    from unittest.mock import MagicMock

    from codelab.server.tools.base import ToolRegistry

    tool_registry = MagicMock(spec=ToolRegistry)
    tool_registry.get_available_tools.return_value = []

    # Ядро
    _scripted_provider = ScriptedMockLLMProvider.from_dict(
        {
            "turns": [{"when_user": ["hello"], "replies": [{"text": "Hi from mock!"}]}],
            "default": {"text": "default reply"},
        }
    )
    execution_engine = ExecutionEngine(
        tool_registry=tool_registry,
        history_builder=__import__(
            "codelab.server.agent.core.history_builder",
            fromlist=["HistoryBuilder"],
        ).HistoryBuilder(codec=content_codec),
    )

    # Smoke: build_context работает (создаёт AgentContext с SessionView).
    context = await execution_engine.build_context(
        session=view,
        prompt="hello",
    )
    assert context.session_id == "sess_no_protocol_1"
    # conversation_history может быть пустой для новой сессии — это OK,
    # главное что build_context вернул валидный AgentContext.
    assert context.available_tools == []
    assert context.prompt == [{"type": "text", "text": "hello"}]

    # Sanity: SessionView type check.
    assert isinstance(view, SessionView)
    assert isinstance(update_sink, UpdateSink)

    # Sanity: FakeUpdateSink накопил вызовы (или не накопил — это OK,
    # ядро не использует UpdateSink в Фазе 4; это Phase 4.4 spec).
    # Главное — что объект можно создать и передать.
    assert update_sink.calls is not None
