"""Unit-тесты для LlmCaller.

Проверяют:
- выбор execute (первая итерация с prompt) vs continue_execution;
- стриминг: дельты через on_delta → streamed=True, эмит через sink;
- отсутствие дельт → streamed=False (полный текст эмитит AgentLoop);
- ensure_strategy_selected — реинициализация стратегии для continue_execution.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.handlers.pipeline.stages.agent_loop.llm_caller import LlmCaller


def _make_caller(strategy: MagicMock, *, streaming: bool = False) -> LlmCaller:
    spb = MagicMock()
    spb.build.return_value = "system prompt"
    return LlmCaller(strategy, spb, streaming_enabled=streaming)


def _session() -> MagicMock:
    session = MagicMock()
    session.session_id = "s1"
    return session


@pytest.mark.asyncio
async def test_first_iteration_with_prompt_calls_execute() -> None:
    strategy = MagicMock()
    strategy.execute = AsyncMock(return_value=MagicMock())
    strategy.continue_execution = AsyncMock()
    caller = _make_caller(strategy)

    await caller.call(_session(), "hello", None, iteration=1, sink=MagicMock())

    strategy.execute.assert_called_once()
    strategy.continue_execution.assert_not_called()


@pytest.mark.asyncio
async def test_later_iteration_calls_continue_execution() -> None:
    strategy = MagicMock()
    strategy.execute = AsyncMock()
    strategy.continue_execution = AsyncMock(return_value=MagicMock())
    caller = _make_caller(strategy)

    await caller.call(_session(), None, None, iteration=2, sink=MagicMock())

    strategy.continue_execution.assert_called_once()
    strategy.execute.assert_not_called()


@pytest.mark.asyncio
async def test_streaming_deltas_mark_streamed_and_emit() -> None:
    async def execute(session, prompt, mcp_manager, *, system_prompt, on_delta):
        await on_delta("chunk-1")
        await on_delta("chunk-2")
        return MagicMock()

    strategy = MagicMock()
    strategy.execute = AsyncMock(side_effect=execute)
    caller = _make_caller(strategy, streaming=True)
    sink = MagicMock()
    sink.emit_streaming_delta = AsyncMock()

    result = await caller.call(_session(), "hi", None, iteration=1, sink=sink)

    assert result.streamed is True
    assert sink.emit_streaming_delta.await_count == 2


@pytest.mark.asyncio
async def test_streaming_enabled_but_no_deltas_leaves_streamed_false() -> None:
    strategy = MagicMock()
    strategy.execute = AsyncMock(return_value=MagicMock())  # не зовёт on_delta
    caller = _make_caller(strategy, streaming=True)
    sink = MagicMock()
    sink.emit_streaming_delta = AsyncMock()

    result = await caller.call(_session(), "hi", None, iteration=1, sink=sink)

    assert result.streamed is False
    sink.emit_streaming_delta.assert_not_called()


@pytest.mark.asyncio
async def test_streaming_disabled_passes_no_on_delta() -> None:
    strategy = MagicMock()
    strategy.execute = AsyncMock(return_value=MagicMock())
    caller = _make_caller(strategy, streaming=False)

    result = await caller.call(_session(), "hi", None, iteration=1, sink=MagicMock())

    assert result.streamed is False
    assert strategy.execute.call_args.kwargs["on_delta"] is None


def test_ensure_strategy_selected_reinitializes_when_unset() -> None:
    strategy = MagicMock()
    strategy._current_strategy_name = None
    strategy.select_strategy = MagicMock()
    caller = _make_caller(strategy)

    caller.ensure_strategy_selected(_session(), "s1")

    strategy.select_strategy.assert_called_once()


def test_ensure_strategy_selected_noop_when_already_set() -> None:
    strategy = MagicMock()
    strategy._current_strategy_name = "single"
    strategy.select_strategy = MagicMock()
    caller = _make_caller(strategy)

    caller.ensure_strategy_selected(_session(), "s1")

    strategy.select_strategy.assert_not_called()
