"""Benchmarks для компонентов декомпозиции ChatViewModel.

Измеряют производительность ключевых операций:
- Dispatcher: маршрутизация обновлений
- Persistence: сохранение/загрузка сообщений
- Observable: уведомление observers
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from codelab.client.presentation.chat.chat_session_state import ChatSessionState
from codelab.client.presentation.chat.context import ChatUpdateContext
from codelab.client.presentation.chat.dispatcher.session_update_dispatcher import (
    SessionUpdateDispatcher,
)
from codelab.client.presentation.chat.handlers.config_option_handler import (
    ConfigOptionHandler,
)
from codelab.client.presentation.chat.handlers.message_chunk_handler import (
    MessageChunkHandler,
)
from codelab.client.presentation.chat.handlers.plan_update_handler import (
    PlanUpdateHandler,
)
from codelab.client.presentation.chat.handlers.tool_call_handler import ToolCallHandler
from codelab.client.presentation.chat.persistence.file_chat_persistence import (
    FileChatPersistence,
)
from codelab.client.presentation.observable import Observable


class TestDispatcherBenchmark:
    """Benchmarks для SessionUpdateDispatcher."""

    @pytest.fixture
    def dispatcher(self) -> SessionUpdateDispatcher:
        """Создает SessionUpdateDispatcher."""
        return SessionUpdateDispatcher(
            message_chunk_handler=MessageChunkHandler(),
            tool_call_handler=ToolCallHandler(),
            plan_update_handler=PlanUpdateHandler(),
            config_option_handler=ConfigOptionHandler(),
        )

    @pytest.fixture
    def context(self) -> ChatUpdateContext:
        """Создает ChatUpdateContext."""
        state = ChatSessionState()
        return ChatUpdateContext(session_id="test-session", state=state)

    def test_dispatch_1000_updates(
        self, dispatcher: SessionUpdateDispatcher, context: ChatUpdateContext
    ) -> None:
        """Измеряет время обработки 1000 обновлений."""
        updates = [
            {
                "params": {
                    "sessionId": "test-session",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"text": f"Message {i}"},
                    },
                }
            }
            for i in range(1000)
        ]

        start = time.perf_counter()
        for update in updates:
            dispatcher.dispatch_with_context(update, context)
        elapsed = time.perf_counter() - start

        # Должно обрабатывать 1000 обновлений менее чем за 100ms
        assert elapsed < 0.1, f"Too slow: {elapsed:.3f}s for 1000 updates"
        print(f"\nDispatch 1000 updates: {elapsed*1000:.2f}ms")

    def test_dispatch_mixed_types(
        self, dispatcher: SessionUpdateDispatcher, context: ChatUpdateContext
    ) -> None:
        """Измеряет время обработки смешанных типов обновлений."""
        updates = []
        for i in range(250):
            updates.extend([
                {
                    "params": {
                        "sessionId": "test-session",
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"text": f"Message {i}"},
                        },
                    }
                },
                {
                    "params": {
                        "sessionId": "test-session",
                        "update": {
                            "sessionUpdate": "tool_call",
                            "toolCallId": f"tc-{i}",
                            "title": f"Tool {i}",
                            "status": "pending",
                        },
                    }
                },
                {
                    "params": {
                        "sessionId": "test-session",
                        "update": {
                            "sessionUpdate": "tool_call_update",
                            "toolCallId": f"tc-{i}",
                            "status": "completed",
                        },
                    }
                },
                {
                    "params": {
                        "sessionId": "test-session",
                        "update": {
                            "sessionUpdate": "plan",
                            "entries": [{"content": f"Step {i}"}],
                        },
                    }
                },
            ])

        start = time.perf_counter()
        for update in updates:
            dispatcher.dispatch_with_context(update, context)
        elapsed = time.perf_counter() - start

        # 1000 смешанных обновлений
        assert elapsed < 0.2, f"Too slow: {elapsed:.3f}s for 1000 mixed updates"
        print(f"\nDispatch 1000 mixed updates: {elapsed*1000:.2f}ms")


class TestPersistenceBenchmark:
    """Benchmarks для FileChatPersistence."""

    @pytest.fixture
    def persistence(self, tmp_path: Path) -> FileChatPersistence:
        """Создает FileChatPersistence."""
        return FileChatPersistence(tmp_path / "history")

    async def test_save_100_messages(self, persistence: FileChatPersistence) -> None:
        """Измеряет время сохранения 100 сообщений."""
        messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
            for i in range(100)
        ]

        start = time.perf_counter()
        await persistence.save_messages("test-session", messages)
        elapsed = time.perf_counter() - start

        # Сохранение 100 сообщений должно быть менее 50ms
        assert elapsed < 0.05, f"Too slow: {elapsed:.3f}s for 100 messages"
        print(f"\nSave 100 messages: {elapsed*1000:.2f}ms")

    async def test_save_1000_messages(self, persistence: FileChatPersistence) -> None:
        """Измеряет время сохранения 1000 сообщений."""
        messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
            for i in range(1000)
        ]

        start = time.perf_counter()
        await persistence.save_messages("test-session", messages)
        elapsed = time.perf_counter() - start

        # Сохранение 1000 сообщений должно быть менее 200ms
        assert elapsed < 0.2, f"Too slow: {elapsed:.3f}s for 1000 messages"
        print(f"\nSave 1000 messages: {elapsed*1000:.2f}ms")

    async def test_load_1000_messages(self, persistence: FileChatPersistence) -> None:
        """Измеряет время загрузки 1000 сообщений."""
        # Сначала сохраняем
        messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
            for i in range(1000)
        ]
        await persistence.save_messages("test-session", messages)

        # Затем загружаем
        start = time.perf_counter()
        loaded = await persistence.load_messages("test-session")
        elapsed = time.perf_counter() - start

        assert len(loaded) == 1000
        # Загрузка 1000 сообщений должна быть менее 100ms
        assert elapsed < 0.1, f"Too slow: {elapsed:.3f}s to load 1000 messages"
        print(f"\nLoad 1000 messages: {elapsed*1000:.2f}ms")

    async def test_rapid_saves(self, persistence: FileChatPersistence) -> None:
        """Измеряет время множественных быстрых сохранений (имитация streaming)."""
        messages = []

        start = time.perf_counter()
        for i in range(100):
            messages.append({"role": "assistant", "content": f"Chunk {i}"})
            await persistence.save_messages("test-session", messages)
        elapsed = time.perf_counter() - start

        # 100 последовательных сохранений должны быть менее 500ms
        assert elapsed < 0.5, f"Too slow: {elapsed:.3f}s for 100 rapid saves"
        print(f"\n100 rapid saves: {elapsed*1000:.2f}ms ({elapsed*10:.2f}ms per save)")


class TestObservableBenchmark:
    """Benchmarks для Observable."""

    def test_observable_1000_updates(self) -> None:
        """Измеряет время 1000 обновлений Observable."""
        obs = Observable(-1)  # Начальное значение отличается от первого присваиваемого
        counter = [0]

        def observer(value: int) -> None:
            counter[0] += 1

        obs.subscribe(observer)

        start = time.perf_counter()
        for i in range(1000):
            obs.value = i
        elapsed = time.perf_counter() - start

        assert counter[0] == 1000
        # 1000 обновлений должны быть менее 50ms
        assert elapsed < 0.05, f"Too slow: {elapsed:.3f}s for 1000 updates"
        print(f"\nObservable 1000 updates: {elapsed*1000:.2f}ms")

    def test_observable_multiple_observers(self) -> None:
        """Измеряет время уведомлений с множественными observers."""
        obs = Observable(-1)  # Начальное значение отличается от первого присваиваемого
        num_observers = 100
        counters = [0] * num_observers

        for i in range(num_observers):
            obs.subscribe(lambda v, idx=i: counters.__setitem__(idx, counters[idx] + 1))

        start = time.perf_counter()
        for i in range(100):
            obs.value = i
        elapsed = time.perf_counter() - start

        # Все observers должны быть уведомлены
        assert all(c == 100 for c in counters)
        # 100 обновлений с 100 observers должны быть менее 100ms
        assert elapsed < 0.1, f"Too slow: {elapsed:.3f}s for 100 updates with 100 observers"
        print(f"\nObservable 100 updates with 100 observers: {elapsed*1000:.2f}ms")


class TestDebounceBenchmark:
    """Benchmarks для debounce механизма persistence."""

    @pytest.fixture
    def persistence(self, tmp_path: Path) -> FileChatPersistence:
        """Создает FileChatPersistence."""
        return FileChatPersistence(tmp_path / "history")

    async def test_debounce_streaming_simulation(
        self, persistence: FileChatPersistence
    ) -> None:
        """Имитирует streaming с debounce - 100 chunks должны сохранить только 1 раз."""
        from unittest.mock import MagicMock

        from codelab.client.presentation.chat_view_model import ChatViewModel

        # Создаем ChatViewModel с persistence
        vm = ChatViewModel(
            coordinator=MagicMock(),
            event_bus=MagicMock(),
            chat_persistence=persistence,
        )
        vm._save_debounce_ms = 50  # Уменьшаем для теста

        # Патчим save_messages чтобы считать вызовы
        save_count = [0]
        original_save = persistence.save_messages

        async def counting_save(*args: Any, **kwargs: Any) -> None:
            save_count[0] += 1
            await original_save(*args, **kwargs)

        persistence.save_messages = counting_save

        # Имитируем streaming: 100 быстрых вызовов _persist_messages
        messages = []
        start = time.perf_counter()
        for i in range(100):
            messages.append({"role": "assistant", "content": f"Chunk {i}"})
            vm._persist_messages("test-session", messages)

        # Ждем завершения debounce
        await vm.flush_pending_saves()
        elapsed = time.perf_counter() - start

        # Должно быть только 1 реальное сохранение благодаря debounce
        assert save_count[0] == 1, f"Expected 1 save, got {save_count[0]}"
        print(f"\nDebounce streaming (100 chunks): {elapsed*1000:.2f}ms, saves: {save_count[0]}")
