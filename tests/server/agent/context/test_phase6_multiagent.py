"""Unit тесты для Phase 6 — Мультиагент (ChildSessionManager, process_subagent_response)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.context.child_session import DefaultChildSessionManager
from codelab.server.agent.context.interfaces import ConversationSummarizer
from codelab.server.agent.context.manager import DefaultContextManager
from codelab.server.agent.context.models import ContextConfig, SubagentResult
from codelab.server.agent.context.token_counter import ApproximateTokenCounter
from codelab.server.llm.models import LLMMessage
from codelab.server.protocol.session_factory import SessionFactory
from codelab.server.protocol.state import SessionState
from codelab.server.storage.base import SessionStorage


class MockSessionFactory(SessionFactory):
    """Mock SessionFactory для тестирования."""

    def create_session(
        self,
        cwd: str,
        mcp_servers: list | None = None,
        session_id: str | None = None,
        **kwargs,
    ) -> SessionState:
        return SessionState(
            session_id=session_id or "mock_session_id",
            cwd=cwd,
            mcp_servers=mcp_servers or [],
            **kwargs,
        )


class MockSessionStorage(SessionStorage):
    """Mock SessionStorage для тестирования."""

    def __init__(self) -> None:
        self.sessions: dict[str, SessionState] = {}

    async def save_session(self, session: SessionState) -> None:
        self.sessions[session.session_id] = session

    async def load_session(self, session_id: str) -> SessionState | None:
        return self.sessions.get(session_id)

    async def list_sessions(
        self,
        cwd: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[SessionState], str | None]:
        sessions = list(self.sessions.values())
        if cwd:
            sessions = [s for s in sessions if s.cwd == cwd]
        return sessions[:limit], None

    async def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    async def session_exists(self, session_id: str) -> bool:
        return session_id in self.sessions


class MockSummarizer(ConversationSummarizer):
    """Mock ConversationSummarizer для тестирования."""

    def __init__(self, summary_text: str = "Mock summary") -> None:
        self.summary_text = summary_text
        self.call_count = 0

    async def summarize(self, messages: list, target_tokens: int = 2000) -> LLMMessage:
        self.call_count += 1
        return LLMMessage(role="assistant", content=self.summary_text)


class TestDefaultChildSessionManager:
    """Тесты для DefaultChildSessionManager."""

    @pytest.fixture
    def mock_session_factory(self) -> MockSessionFactory:
        return MockSessionFactory()

    @pytest.fixture
    def mock_session_storage(self) -> MockSessionStorage:
        return MockSessionStorage()

    @pytest.fixture
    def mock_summarizer(self) -> MockSummarizer:
        return MockSummarizer()

    @pytest.fixture
    def token_counter(self) -> ApproximateTokenCounter:
        return ApproximateTokenCounter()

    @pytest.fixture
    def child_session_manager(
        self,
        mock_session_factory: MockSessionFactory,
        mock_session_storage: MockSessionStorage,
        mock_summarizer: MockSummarizer,
        token_counter: ApproximateTokenCounter,
    ) -> DefaultChildSessionManager:
        return DefaultChildSessionManager(
            session_factory=mock_session_factory,
            session_storage=mock_session_storage,
            summarizer=mock_summarizer,
            token_counter=token_counter,
        )

    @pytest.mark.asyncio
    async def test_create_child_session(
        self, child_session_manager: DefaultChildSessionManager
    ) -> None:
        """Тест создания child-сессии."""
        parent = SessionState(
            session_id="parent_session",
            cwd="/test/project",
            mcp_servers=[],
        )

        child = await child_session_manager.create_child(parent, "coder")

        assert child is not None
        assert child.session_id == "parent_session_child_coder"
        assert child.cwd == "/test/project"
        assert child.config_values["parent_session_id"] == "parent_session"
        assert child.config_values["subagent_scope"] == "coder"

    @pytest.mark.asyncio
    async def test_collect_summary_with_history(
        self, child_session_manager: DefaultChildSessionManager
    ) -> None:
        """Тест сбора summary из child-сессии с историей."""
        child = SessionState(
            session_id="child_session",
            cwd="/test/project",
            mcp_servers=[],
            history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
        )
        child.config_values["subagent_scope"] = "coder"

        result = await child_session_manager.collect_summary(child)

        assert isinstance(result, SubagentResult)
        assert result.summary == "Mock summary"
        assert result.source_scope == "coder"
        assert result.token_count > 0

    @pytest.mark.asyncio
    async def test_collect_summary_empty_history(
        self, child_session_manager: DefaultChildSessionManager
    ) -> None:
        """Тест сбора summary из child-сессии без истории."""
        child = SessionState(
            session_id="child_session",
            cwd="/test/project",
            mcp_servers=[],
            history=[],
        )
        child.config_values["subagent_scope"] = "coder"

        result = await child_session_manager.collect_summary(child)

        assert isinstance(result, SubagentResult)
        assert result.summary == "(субагент не выполнил действий)"
        assert result.token_count == 0
        assert result.source_scope == "coder"


class TestProcessSubagentResponse:
    """Тесты для process_subagent_response в DefaultContextManager."""

    @pytest.fixture
    def mock_tool_registry(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def context_manager(self, mock_tool_registry: MagicMock) -> DefaultContextManager:
        config = ContextConfig(enabled=True)
        return DefaultContextManager(
            tool_registry=mock_tool_registry,
            config=config,
            summarizer=MockSummarizer("Summarized response"),
            token_counter=ApproximateTokenCounter(),
        )

    @pytest.mark.asyncio
    async def test_process_empty_response(self, context_manager: DefaultContextManager) -> None:
        """Тест обработки пустого ответа."""
        result = await context_manager.process_subagent_response(
            parent_scope="parent",
            subagent_scope="child",
            response=None,
        )

        assert result.summary == "(субагент не выполнил действий)"
        assert result.token_count == 0
        assert result.source_scope == "child"

    @pytest.mark.asyncio
    async def test_process_string_response(self, context_manager: DefaultContextManager) -> None:
        """Тест обработки строкового ответа (fallback — обрезка до 500 символов)."""
        response_text = "This is a test response from the subagent."
        result = await context_manager.process_subagent_response(
            parent_scope="parent",
            subagent_scope="child",
            response=response_text,
        )

        assert result.summary == response_text
        assert result.token_count > 0
        assert result.source_scope == "child"

    @pytest.mark.asyncio
    async def test_process_list_messages_response(
        self, context_manager: DefaultContextManager
    ) -> None:
        """Тест обработки списка сообщений."""
        from codelab.server.llm.models import LLMMessage

        messages = [
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi there"),
        ]

        result = await context_manager.process_subagent_response(
            parent_scope="parent",
            subagent_scope="child",
            response=messages,
        )

        assert result.summary == "Summarized response"
        assert result.token_count > 0
        assert result.source_scope == "child"

    @pytest.mark.asyncio
    async def test_process_dict_response(self, context_manager: DefaultContextManager) -> None:
        """Тест обработки dict-ответа (fallback — извлекает content)."""
        response_dict = {"content": "Dict response content"}
        result = await context_manager.process_subagent_response(
            parent_scope="parent",
            subagent_scope="child",
            response=response_dict,
        )

        assert result.summary == "Dict response content"
        assert result.token_count > 0
        assert result.source_scope == "child"
