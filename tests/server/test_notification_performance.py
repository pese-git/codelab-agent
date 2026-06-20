"""Performance benchmarks для notification delivery.

Измеряет latency отправки notifications через immediate delivery callback.
Цель: убедиться что latency < 100ms для real-time UX.
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop


@pytest.fixture
def mock_strategy():
    """Mock LLMCallStrategy."""
    strategy = MagicMock()
    strategy.execute = AsyncMock()
    strategy.continue_execution = AsyncMock()
    return strategy


@pytest.fixture
def mock_dependencies():
    """Mock зависимости AgentLoop."""
    mock_spb = MagicMock()
    mock_spb.build.return_value = "You are a helpful assistant."
    return {
        "tool_registry": MagicMock(),
        "tool_call_handler": MagicMock(),
        "permission_manager": MagicMock(),
        "state_manager": MagicMock(),
        "content_extractor": AsyncMock(),
        "content_validator": MagicMock(),
        "content_formatter": MagicMock(),
        "replay_manager": MagicMock(),
        "plan_builder": MagicMock(),
        "system_prompt_builder": mock_spb,
    }


class TestNotificationPerformanceBenchmark:
    """Performance benchmarks для notification delivery."""

    @pytest.mark.asyncio
    async def test_notification_latency_benchmark(
        self, mock_strategy, mock_dependencies
    ):
        """Измерить latency для 100 notifications."""
        latencies = []

        async def mock_callback(notification: ACPMessage) -> None:
            # Имитация работы transport
            pass

        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=mock_callback,
        )

        # Измерение latency для 100 notifications
        for i in range(100):
            notification = ACPMessage.notification(
                "session/update",
                {
                    "sessionId": "test_session",
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": f"call_{i:03d}",
                        "status": "completed",
                        "content": [
                            {"type": "text", "text": f"Notification {i}"},
                        ],
                    },
                },
            )

            start_time = time.time()
            await loop._send_notification_immediately(notification)
            end_time = time.time()

            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)

        # Статистика
        avg_latency = sum(latencies) / len(latencies)
        sorted_latencies = sorted(latencies)
        p50_latency = sorted_latencies[len(sorted_latencies) // 2]
        p95_latency = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        p99_latency = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        max_latency = max(latencies)

        # Вывод статистики для отладки
        print(f"\nNotification Latency Statistics (n={len(latencies)}):")
        print(f"  Average: {avg_latency:.2f}ms")
        print(f"  P50:     {p50_latency:.2f}ms")
        print(f"  P95:     {p95_latency:.2f}ms")
        print(f"  P99:     {p99_latency:.2f}ms")
        print(f"  Max:     {max_latency:.2f}ms")

        # Проверки
        assert avg_latency < 50, f"Average latency {avg_latency}ms > 50ms"
        assert p95_latency < 100, f"P95 latency {p95_latency}ms > 100ms"
        assert p99_latency < 200, f"P99 latency {p99_latency}ms > 200ms"

    @pytest.mark.asyncio
    async def test_terminal_embedding_latency_benchmark(
        self, mock_strategy, mock_dependencies
    ):
        """Измерить latency для terminal embedding notifications."""
        latencies = []

        async def mock_callback(notification: ACPMessage) -> None:
            # Имитация работы transport
            pass

        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=mock_callback,
        )

        # Измерение latency для 100 terminal embedding notifications
        for i in range(100):
            notification = ACPMessage.notification(
                "session/update",
                {
                    "sessionId": "test_session",
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": f"call_{i:03d}",
                        "status": "completed",
                        "content": [
                            {"type": "terminal", "terminalId": f"term_{i:03d}"},
                            {
                                "type": "content",
                                "content": {
                                    "type": "text",
                                    "text": f"Terminal {i} created",
                                },
                            },
                        ],
                    },
                },
            )

            start_time = time.time()
            await loop._send_notification_immediately(notification)
            end_time = time.time()

            latency_ms = (end_time - start_time) * 1000
            latencies.append(latency_ms)

        # Статистика
        avg_latency = sum(latencies) / len(latencies)
        sorted_latencies = sorted(latencies)
        p50_latency = sorted_latencies[len(sorted_latencies) // 2]
        p95_latency = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        p99_latency = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        max_latency = max(latencies)

        # Вывод статистики для отладки
        print(f"\nTerminal Embedding Latency Statistics (n={len(latencies)}):")
        print(f"  Average: {avg_latency:.2f}ms")
        print(f"  P50:     {p50_latency:.2f}ms")
        print(f"  P95:     {p95_latency:.2f}ms")
        print(f"  P99:     {p99_latency:.2f}ms")
        print(f"  Max:     {max_latency:.2f}ms")

        # Проверки
        assert avg_latency < 50, f"Average latency {avg_latency}ms > 50ms"
        assert p95_latency < 100, f"P95 latency {p95_latency}ms > 100ms"
        assert p99_latency < 200, f"P99 latency {p99_latency}ms > 200ms"

    @pytest.mark.asyncio
    async def test_callback_overhead_benchmark(
        self, mock_strategy, mock_dependencies
    ):
        """Измерить overhead от использования callback."""
        # Измерение без callback
        loop_without_callback = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=None,
        )

        notification = ACPMessage.notification(
            "session/update",
            {
                "sessionId": "test_session",
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                },
            },
        )

        # Измерение без callback
        start_time = time.time()
        for _ in range(1000):
            await loop_without_callback._send_notification_immediately(notification)
        end_time = time.time()
        time_without_callback_ms = (end_time - start_time) * 1000

        # Измерение с callback
        async def mock_callback(notification: ACPMessage) -> None:
            pass

        loop_with_callback = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=mock_callback,
        )

        start_time = time.time()
        for _ in range(1000):
            await loop_with_callback._send_notification_immediately(notification)
        end_time = time.time()
        time_with_callback_ms = (end_time - start_time) * 1000

        # Вычисление overhead
        overhead_ms = time_with_callback_ms - time_without_callback_ms
        if time_without_callback_ms > 0:
            overhead_percent = (overhead_ms / time_without_callback_ms * 100)
        else:
            overhead_percent = 0

        print("\nCallback Overhead Statistics (n=1000):")
        print(f"  Without callback: {time_without_callback_ms:.2f}ms")
        print(f"  With callback:    {time_with_callback_ms:.2f}ms")
        print(f"  Overhead:         {overhead_ms:.2f}ms ({overhead_percent:.2f}%)")

        # Overhead должен быть приемлемым (< 500% для async callback)
        # Note: async callback добавляет overhead, но absolute latency всё ещё очень низкая
        assert overhead_percent < 500, f"Callback overhead {overhead_percent}% > 500%"
        
        #更重要的是: absolute latency с callback всё ещё должна быть < 100ms
        avg_latency_with_callback = time_with_callback_ms / 1000
        error_msg = f"Average latency with callback {avg_latency_with_callback}ms > 0.1ms"
        assert avg_latency_with_callback < 0.1, error_msg
