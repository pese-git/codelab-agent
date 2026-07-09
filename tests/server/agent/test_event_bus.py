"""Integration и unit тесты для AgentEventBus."""

import asyncio
import time

import pytest

from codelab.server.agent.contracts.base import (
    AgentDispatchError,
    AgentNotFoundError,
    AgentRegistered,
    AgentRequest,
    AgentResponse,
    AgentResult,
    AgentUnregistered,
    BroadcastPartialFailure,
    ChoreographyAnswer,
    ContextBroadcast,
    DomainEvent,
    TokenUsage,
    ToolCall,
)
from codelab.server.agent.event_bus.bus import AgentEventBus, RetryConfig


class SampleEvent(DomainEvent):
    pass


class MockRequestHandler:
    """Mock RequestHandler для тестов."""

    def __init__(
        self,
        result: AgentResult | None = None,
        should_fail: bool = False,
        fail_count: int = 0,
    ) -> None:
        self.result = result or AgentResult(text="mock response", agent_name="mock")
        self.should_fail = should_fail
        self.fail_count = fail_count
        self.call_count = 0
        self.received_requests: list[AgentRequest] = []

    async def __call__(
        self,
        request: AgentRequest,
        parent_span: object = None,
    ) -> AgentResponse:
        self.call_count += 1
        self.received_requests.append(request)

        if self.should_fail or (self.fail_count > 0 and self.call_count <= self.fail_count):
            raise RuntimeError(f"Handler failed on attempt {self.call_count}")

        return AgentResponse(
            request_id=request.correlation_id,
            text=self.result.text,
            tool_calls=self.result.tool_calls,
            usage=self.result.usage,
            stop_reason=self.result.stop_reason,
            agent_name=self.result.agent_name,
            session_id=request.session_id,
        )


@pytest.fixture
def bus():
    return AgentEventBus(retry_config=RetryConfig(max_attempts=3, base_delay=0.01))


# ─────────────────────────────────────────────
# 4.11 — subscribe/unsubscribe lifecycle
# ─────────────────────────────────────────────


class TestSubscribeUnsubscribeLifecycle:
    @pytest.mark.asyncio
    async def test_subscribe_and_unsubscribe(self, bus):
        received = []

        async def handler(event: DomainEvent) -> None:
            received.append(event)

        sub = bus.subscribe(SampleEvent, handler)
        assert sub.is_active is True

        await bus.publish(SampleEvent(session_id="test"))
        assert len(received) == 1

        bus.unsubscribe(sub)
        assert sub.is_active is False

        await bus.publish(SampleEvent(session_id="test"))
        assert len(received) == 1  # Не изменилось

    @pytest.mark.asyncio
    async def test_multiple_handlers_unsubscribe_one(self, bus):
        received = []

        async def handler1(event: DomainEvent) -> None:
            received.append(1)

        async def handler2(event: DomainEvent) -> None:
            received.append(2)

        sub1 = bus.subscribe(SampleEvent, handler1)
        bus.subscribe(SampleEvent, handler2)

        await bus.publish(SampleEvent(session_id="test"))
        assert received == [1, 2]

        bus.unsubscribe(sub1)
        received.clear()

        await bus.publish(SampleEvent(session_id="test"))
        assert received == [2]


# ─────────────────────────────────────────────
# 4.12 — publish с несколькими подписчиками
# ─────────────────────────────────────────────


class TestPublishMultipleSubscribers:
    @pytest.mark.asyncio
    async def test_three_subscribers(self, bus):
        received = []

        async def make_handler(n):
            async def handler(event: DomainEvent) -> None:
                received.append(n)

            return handler

        for i in range(3):
            bus.subscribe(SampleEvent, await make_handler(i))

        await bus.publish(SampleEvent(session_id="test"))
        assert sorted(received) == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_different_event_types(self, bus):
        class EventA(DomainEvent):
            pass

        class EventB(DomainEvent):
            pass

        received_a = []
        received_b = []

        async def handler_a(event: DomainEvent) -> None:
            received_a.append(1)

        async def handler_b(event: DomainEvent) -> None:
            received_b.append(1)

        bus.subscribe(EventA, handler_a)
        bus.subscribe(EventB, handler_b)

        await bus.publish(EventA(session_id="test"))
        assert received_a == [1]
        assert received_b == []

        await bus.publish(EventB(session_id="test"))
        assert received_a == [1]
        assert received_b == [1]


# ─────────────────────────────────────────────
# 4.13 — publish с ошибкой одного подписчика
# ─────────────────────────────────────────────


class TestPublishWithError:
    @pytest.mark.asyncio
    async def test_one_handler_fails_others_continue(self, bus):
        received = []

        async def bad_handler(event: DomainEvent) -> None:
            raise ValueError("boom")

        async def good_handler1(event: DomainEvent) -> None:
            received.append(1)

        async def good_handler2(event: DomainEvent) -> None:
            received.append(2)

        bus.subscribe(SampleEvent, bad_handler)
        bus.subscribe(SampleEvent, good_handler1)
        bus.subscribe(SampleEvent, good_handler2)

        await bus.publish(SampleEvent(session_id="test"))
        assert 1 in received
        assert 2 in received


# ─────────────────────────────────────────────
# 4.14 — integration: register_agent → send_request → AgentResponse
# ─────────────────────────────────────────────


class TestRegisterSendRequest:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self, bus):
        handler = MockRequestHandler(
            result=AgentResult(
                text="hello",
                tool_calls=[ToolCall(id="tc1", name="read_file")],
                usage=TokenUsage(10, 20, 30),
                stop_reason="end_turn",
                agent_name="coder",
            )
        )

        await bus.register_agent("coder", handler)
        assert handler.call_count == 0

        request = AgentRequest(
            target_agent="coder",
            correlation_id="corr_1",
            session_id="sess_1",
        )

        response = await bus.send_request(request)

        assert handler.call_count == 1
        assert isinstance(response, AgentResponse)
        assert response.request_id == "corr_1"
        assert response.text == "hello"
        assert len(response.tool_calls) == 1
        assert response.usage == TokenUsage(10, 20, 30)
        assert response.stop_reason == "end_turn"
        assert response.agent_name == "coder"

    @pytest.mark.asyncio
    async def test_agent_not_found(self, bus):
        request = AgentRequest(
            target_agent="nonexistent",
            correlation_id="corr_1",
            session_id="sess_1",
        )

        with pytest.raises(AgentNotFoundError, match="not registered"):
            await bus.send_request(request)

    @pytest.mark.asyncio
    async def test_unregister_agent(self, bus):
        handler = MockRequestHandler()
        await bus.register_agent("temp", handler)
        await bus.unregister_agent("temp")

        request = AgentRequest(
            target_agent="temp",
            correlation_id="corr_1",
            session_id="sess_1",
        )

        with pytest.raises(AgentNotFoundError):
            await bus.send_request(request)

    @pytest.mark.asyncio
    async def test_unregister_nonexistent(self, bus):
        # Не должно вызывать ошибку
        await bus.unregister_agent("nonexistent")

    @pytest.mark.asyncio
    async def test_publishes_lifecycle_events(self, bus):
        received = []

        async def handler(event: DomainEvent) -> None:
            received.append(event)

        bus.subscribe(AgentRegistered, handler)
        bus.subscribe(AgentUnregistered, handler)

        mock = MockRequestHandler()
        await bus.register_agent("coder", mock)
        await bus.unregister_agent("coder")

        assert len(received) == 2
        assert isinstance(received[0], AgentRegistered)
        assert isinstance(received[1], AgentUnregistered)


# ─────────────────────────────────────────────
# 4.15 — integration: broadcast → list[ChoreographyAnswer]
# ─────────────────────────────────────────────


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_to_two_agents(self, bus):
        handler1 = MockRequestHandler(
            result=AgentResult(text="response1", agent_name="coder")
        )
        handler2 = MockRequestHandler(
            result=AgentResult(text="response2", agent_name="reviewer")
        )

        await bus.register_agent("coder", handler1)
        await bus.register_agent("reviewer", handler2)

        broadcast = ContextBroadcast(
            context=[],
            available_agents=["coder", "reviewer"],
            step=1,
            correlation_id="corr_1",
            session_id="sess_1",
        )

        answers = await bus.broadcast(broadcast)

        assert len(answers) == 2
        assert all(isinstance(a, ChoreographyAnswer) for a in answers)
        names = {a.agent_name for a in answers}
        assert names == {"coder", "reviewer"}

    @pytest.mark.asyncio
    async def test_broadcast_empty_bus(self, bus):
        broadcast = ContextBroadcast(
            context=[],
            session_id="sess_1",
        )
        answers = await bus.broadcast(broadcast)
        assert answers == []


# ─────────────────────────────────────────────
# 4.16 — error tests: AgentNotFoundError, AgentDispatchError, BroadcastPartialFailure
# ─────────────────────────────────────────────


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_agent_not_found_error(self, bus):
        request = AgentRequest(target_agent="ghost", session_id="s1")
        with pytest.raises(AgentNotFoundError) as exc_info:
            await bus.send_request(request)
        assert "ghost" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_agent_dispatch_error_after_retries(self, bus):
        handler = MockRequestHandler(should_fail=True)
        await bus.register_agent("flaky", handler)

        request = AgentRequest(
            target_agent="flaky",
            correlation_id="c1",
            session_id="s1",
        )

        with pytest.raises(AgentDispatchError) as exc_info:
            await bus.send_request(request)

        assert "3 attempts" in str(exc_info.value)
        # Handler был вызван 3 раза (retry)
        assert handler.call_count == 3

    @pytest.mark.asyncio
    async def test_broadcast_partial_failure(self, bus):
        good = MockRequestHandler(result=AgentResult(text="ok", agent_name="good"))
        bad = MockRequestHandler(should_fail=True)

        await bus.register_agent("good", good)
        await bus.register_agent("bad", bad)

        broadcast = ContextBroadcast(session_id="s1")

        with pytest.raises(BroadcastPartialFailure) as exc_info:
            await bus.broadcast(broadcast)

        assert "bad" in exc_info.value.failed_agents
        assert len(exc_info.value.failed_agents) == 1


# ─────────────────────────────────────────────
# 4.17 — retry tests: handler fails twice, succeeds on 3rd
# ─────────────────────────────────────────────


class TestRetryBehavior:
    @pytest.mark.asyncio
    async def test_succeeds_on_third_attempt(self, bus):
        handler = MockRequestHandler(fail_count=2)
        await bus.register_agent("flaky", handler)

        request = AgentRequest(
            target_agent="flaky",
            correlation_id="c1",
            session_id="s1",
        )

        response = await bus.send_request(request)

        assert handler.call_count == 3
        assert response.text == "mock response"

    @pytest.mark.asyncio
    async def test_succeeds_on_first_retry(self, bus):
        handler = MockRequestHandler(fail_count=1)
        await bus.register_agent("flaky", handler)

        request = AgentRequest(
            target_agent="flaky",
            correlation_id="c1",
            session_id="s1",
        )

        response = await bus.send_request(request)

        assert handler.call_count == 2
        assert response.agent_name == "mock"

    @pytest.mark.asyncio
    async def test_no_retry_on_success(self, bus):
        handler = MockRequestHandler()
        await bus.register_agent("stable", handler)

        request = AgentRequest(
            target_agent="stable",
            correlation_id="c1",
            session_id="s1",
        )

        await bus.send_request(request)
        assert handler.call_count == 1


# ─────────────────────────────────────────────
# 4.18 — concurrency tests: parallel publish, parallel send_request
# ─────────────────────────────────────────────


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_parallel_publish(self, bus):
        received = []
        lock = asyncio.Lock()

        async def slow_handler(event: DomainEvent) -> None:
            await asyncio.sleep(0.01)
            async with lock:
                received.append(1)

        for _ in range(5):
            bus.subscribe(SampleEvent, slow_handler)

        start = time.time()
        await bus.publish(SampleEvent(session_id="test"))
        elapsed = time.time() - start

        assert len(received) == 5
        # Параллельное выполнение — должно занять ~0.01s, не 0.05s
        assert elapsed < 0.05

    @pytest.mark.asyncio
    async def test_parallel_send_requests(self, bus):
        handler = MockRequestHandler()
        await bus.register_agent("worker", handler)

        async def send_one(i):
            return await bus.send_request(
                AgentRequest(
                    target_agent="worker",
                    correlation_id=f"c{i}",
                    session_id="s1",
                )
            )

        tasks = [send_one(i) for i in range(5)]
        responses = await asyncio.gather(*tasks)

        assert len(responses) == 5
        assert handler.call_count == 5

    @pytest.mark.asyncio
    async def test_clear_during_operations(self, bus):
        """Тест: clear не ломает активные операции."""
        received = []

        async def slow_handler(event: DomainEvent) -> None:
            await asyncio.sleep(0.01)
            received.append(1)

        bus.subscribe(SampleEvent, slow_handler)

        # Запускаем publish и сразу clear
        task = asyncio.create_task(bus.publish(SampleEvent(session_id="test")))
        await bus.clear()

        # Не должно быть ошибки
        await task


# ─────────────────────────────────────────────
# send_request_streaming — стриминг ответа
# ─────────────────────────────────────────────


class TestSendRequestStreaming:
    """Тесты стримингового пути шины."""

    @pytest.mark.asyncio
    async def test_streaming_yields_deltas_then_final(self, bus):
        """stream_handler отдаёт дельты (str), затем финальный AgentResult;
        шина отдаёт дельты и финальный AgentResponse."""
        async def stream_handler(request, parent_span=None):
            yield "Hel"
            yield "lo"
            yield AgentResult(text="Hello", agent_name="coder", stop_reason="end_turn")

        await bus.register_agent(
            "coder", MockRequestHandler(), stream_handler=stream_handler
        )

        request = AgentRequest(target_agent="coder", session_id="s1", correlation_id="c1")
        items = [item async for item in bus.send_request_streaming(request)]

        deltas = [i for i in items if isinstance(i, str)]
        finals = [i for i in items if isinstance(i, AgentResponse)]
        assert deltas == ["Hel", "lo"]
        assert len(finals) == 1
        assert finals[-1].text == "Hello"
        assert finals[-1].request_id == "c1"
        assert finals[-1].session_id == "s1"

    @pytest.mark.asyncio
    async def test_streaming_falls_back_without_stream_handler(self, bus):
        """Без stream_handler — деградация: только финальный AgentResponse, без дельт."""
        await bus.register_agent(
            "coder",
            MockRequestHandler(AgentResult(text="whole", agent_name="coder")),
        )

        request = AgentRequest(target_agent="coder", session_id="s1", correlation_id="c1")
        items = [item async for item in bus.send_request_streaming(request)]

        assert len(items) == 1
        assert isinstance(items[0], AgentResponse)
        assert items[0].text == "whole"

    @pytest.mark.asyncio
    async def test_streaming_unknown_agent_raises(self, bus):
        """Стриминг к незарегистрированному агенту → AgentNotFoundError."""
        request = AgentRequest(target_agent="ghost", session_id="s1")
        with pytest.raises(AgentNotFoundError):
            async for _ in bus.send_request_streaming(request):
                pass

    @pytest.mark.asyncio
    async def test_streaming_without_final_raises(self, bus):
        """stream_handler без финального AgentResult → AgentDispatchError."""
        async def bad_handler(request, parent_span=None):
            yield "only delta"

        await bus.register_agent("coder", MockRequestHandler(), stream_handler=bad_handler)

        request = AgentRequest(target_agent="coder", session_id="s1")
        with pytest.raises(AgentDispatchError):
            async for _ in bus.send_request_streaming(request):
                pass

    @pytest.mark.asyncio
    async def test_streaming_publishes_final_for_observability(self, bus):
        """Финальный AgentResponse публикуется в шину (как в send_request)."""
        published: list = []

        async def observer(event: DomainEvent) -> None:
            published.append(event)

        bus.subscribe(AgentResponse, observer)

        async def stream_handler(request, parent_span=None):
            yield "x"
            yield AgentResult(text="x", agent_name="coder")

        await bus.register_agent(
            "coder", MockRequestHandler(), stream_handler=stream_handler
        )
        request = AgentRequest(target_agent="coder", session_id="s1")
        async for _ in bus.send_request_streaming(request):
            pass

        assert any(isinstance(e, AgentResponse) for e in published)
