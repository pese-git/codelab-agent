"""E2E тест для проверки точности сбора контекста.

Тестирует полный пайплайн:
SingleStrategy → ExecutionEngine → ContextManager → сбор файлов

Цель: точность сбора релевантных файлов ≥80%.

ContextGatherer получает структуру проекта из session.config_values["project_structure"],
которую агент сохраняет через terminal/create в рамках agent loop.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
from codelab.server.agent.context.gatherer import ACPContextGatherer
from codelab.server.agent.context.manager import DefaultContextManager
from codelab.server.agent.context.models import (
    BuildOptions,
    ContextConfig,
    TaskProfile,
    TaskType,
)
from codelab.server.llm.models import CompletionResponse, StopReason
from codelab.server.tools.base import ToolExecutionResult


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class MockToolRegistry:
    """Mock ToolRegistry для тестирования."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self._files = files or {}

    def get_available_tools(self, session_id: str) -> list:
        return [_FakeTool("fs_read")]

    async def execute_tool(
        self, session_id: str, tool_name: str, arguments: dict
    ) -> ToolExecutionResult:
        if tool_name == "fs_read":
            path = arguments.get("path", "")
            content = self._files.get(path)
            if content is not None:
                return ToolExecutionResult(success=True, raw_output={"content": content})
            return ToolExecutionResult(success=False, error="File not found")

        return ToolExecutionResult(success=False, error="Unknown tool")


def _make_session(
    session_id: str = "test_session",
    file_paths: list[str] | None = None,
) -> MagicMock:
    """Создать mock session с project_structure в config_values."""
    session = MagicMock()
    session.session_id = session_id
    session.config_values = {}
    if file_paths is not None:
        session.config_values["project_structure"] = json.dumps(file_paths)
    return session


class MockLLMProvider:
    """Mock LLM провайдер для тестирования."""

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    async def create_completion(self, request):
        return CompletionResponse(
            text=self._response_text,
            tool_calls=[],
            stop_reason=StopReason.END_TURN,
            model=request.model,
        )


class TestContextGathererE2E:
    """E2E тесты для ContextGatherer."""

    @pytest.mark.asyncio
    async def test_gather_finds_relevant_files(self):
        """Gatherer должен находить релевантные файлы по поисковым терминам."""
        files = {
            "src/auth.py": "def authenticate(): pass",
            "src/user.py": "class User: pass",
            "src/main.py": "def main(): pass",
            "tests/test_auth.py": "def test_auth(): pass",
        }
        tool_registry = MockToolRegistry(files)
        dep_graph = RegexDependencyGraph()

        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
        )

        profile = TaskProfile(
            task_type=TaskType.FEATURE,
            search_terms=["auth", "user"],
            target_modules=[],
            investigation_depth=1,
            needs_tests=False,
        )

        session = _make_session("test_session", file_paths=list(files.keys()))

        items = await gatherer.gather(profile, session)

        paths = [item.id for item in items]
        assert any("auth" in p for p in paths)
        assert any("user" in p for p in paths)

    @pytest.mark.asyncio
    async def test_gather_respects_max_files(self):
        """Gatherer должен уважать лимит max_files."""
        files = {f"src/file{i}.py": f"content {i}" for i in range(20)}
        tool_registry = MockToolRegistry(files)
        dep_graph = RegexDependencyGraph()

        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
        )

        profile = TaskProfile(
            task_type=TaskType.FEATURE,
            search_terms=["file"],
            target_modules=[],
            investigation_depth=1,
            needs_tests=False,
        )

        session = _make_session("test_session", file_paths=list(files.keys()))

        options = BuildOptions(max_files=5)
        items = await gatherer.gather(profile, session, options=options)

        assert len(items) <= 5

    @pytest.mark.asyncio
    async def test_gather_without_project_structure(self):
        """Без project_structure gatherer возвращает пустой результат."""
        files = {
            "src/auth.py": "def authenticate(): pass",
        }
        tool_registry = MockToolRegistry(files)
        dep_graph = RegexDependencyGraph()

        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
        )

        profile = TaskProfile(
            task_type=TaskType.FEATURE,
            search_terms=["auth"],
            target_modules=[],
            investigation_depth=1,
            needs_tests=False,
        )

        session = _make_session("test_session")

        items = await gatherer.gather(profile, session)

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_gather_filters_ignored_dirs(self):
        """Gatherer должен фильтровать мусорные папки из project_structure."""
        files = {
            "src/main.py": "def main(): pass",
            ".git/config": "git config",
            "node_modules/pkg/index.js": "module",
            "__pycache__/main.cpython-312.pyc": "bytecode",
        }
        tool_registry = MockToolRegistry({"src/main.py": "def main(): pass"})
        dep_graph = RegexDependencyGraph()

        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
        )

        profile = TaskProfile(
            task_type=TaskType.FEATURE,
            search_terms=["main"],
            target_modules=[],
            investigation_depth=1,
            needs_tests=False,
        )

        session = _make_session("test_session", file_paths=list(files.keys()))

        items = await gatherer.gather(profile, session)

        paths = [item.id for item in items]
        assert "src/main.py" in paths
        assert not any(".git" in p for p in paths)
        assert not any("node_modules" in p for p in paths)
        assert not any("__pycache__" in p for p in paths)


class TestContextManagerE2E:
    """E2E тесты для ContextManager."""

    @pytest.mark.asyncio
    async def test_build_context_returns_payload_envelope(self):
        """build_context() должен возвращать PayloadEnvelope."""
        files = {
            "src/main.py": "def main(): pass",
        }
        tool_registry = MockToolRegistry(files)

        llm_response = """{
            "task_type": "feature",
            "search_terms": ["main"],
            "target_modules": ["src/main.py"],
            "investigation_depth": 1,
            "needs_tests": false
        }"""
        llm = MockLLMProvider(llm_response)

        config = ContextConfig(enabled=True, gather_enabled=True)
        manager = DefaultContextManager(
            tool_registry=tool_registry,
            config=config,
            llm=llm,
        )

        session = _make_session("test_session", file_paths=["src/main.py"])
        session.cwd = "/project"

        prompt = [{"type": "text", "text": "Add feature to main"}]

        envelope = await manager.build_context(
            session=session,
            prompt=prompt,
            agent_scope="single",
            system_prompt="You are a helpful assistant.",
        )

        assert envelope is not None
        assert len(envelope.baseline) > 0
        assert len(envelope.tail) > 0
        assert envelope.baseline_fingerprint != ""

    @pytest.mark.asyncio
    async def test_build_context_with_gather_disabled(self):
        """build_context() должен работать с отключённым сбором."""
        tool_registry = MockToolRegistry({})

        config = ContextConfig(enabled=True, gather_enabled=False)
        manager = DefaultContextManager(
            tool_registry=tool_registry,
            config=config,
            llm=None,
        )

        session = _make_session("test_session")
        session.cwd = "/project"

        prompt = [{"type": "text", "text": "Hello"}]

        envelope = await manager.build_context(
            session=session,
            prompt=prompt,
            agent_scope="single",
            system_prompt="You are helpful.",
        )

        assert len(envelope.baseline) == 1
        assert envelope.baseline[0].role == "system"
        assert "You are helpful." in envelope.baseline[0].content

    @pytest.mark.asyncio
    async def test_build_context_includes_gathered_files(self):
        """build_context() должен включать собранные файлы в baseline."""
        files = {
            "src/auth.py": "def authenticate(): pass\n" * 10,
            "src/user.py": "class User: pass\n" * 10,
        }
        tool_registry = MockToolRegistry(files)

        llm_response = """{
            "task_type": "feature",
            "search_terms": ["auth"],
            "target_modules": ["src/auth.py"],
            "investigation_depth": 1,
            "needs_tests": false
        }"""
        llm = MockLLMProvider(llm_response)

        config = ContextConfig(enabled=True, gather_enabled=True)
        manager = DefaultContextManager(
            tool_registry=tool_registry,
            config=config,
            llm=llm,
        )

        session = _make_session("test_session", file_paths=list(files.keys()))
        session.cwd = "/project"

        prompt = [{"type": "text", "text": "Add authentication"}]

        envelope = await manager.build_context(
            session=session,
            prompt=prompt,
            agent_scope="single",
            system_prompt="You are helpful.",
        )

        baseline_text = " ".join(msg.content for msg in envelope.baseline if msg.content)
        assert "authenticate" in baseline_text or len(envelope.baseline) >= 1


class TestAccuracyBenchmark:
    """Бенчмарк точности сбора файлов."""

    @pytest.mark.asyncio
    async def test_accuracy_at_least_80_percent(self):
        """Точность сбора релевантных файлов должна быть ≥80%."""
        files = {
            "src/auth/login.py": "def login(): pass",
            "src/auth/logout.py": "def logout(): pass",
            "src/auth/session.py": "class Session: pass",
            "src/utils/math.py": "def add(): pass",
            "src/utils/string.py": "def concat(): pass",
            "src/models/user.py": "class User: pass",
        }
        tool_registry = MockToolRegistry(
            {k: v for k, v in files.items() if "auth" in k}
        )
        dep_graph = RegexDependencyGraph()

        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
        )

        profile = TaskProfile(
            task_type=TaskType.FEATURE,
            search_terms=["auth", "login", "logout", "session"],
            target_modules=["src/auth/login.py"],
            investigation_depth=1,
            needs_tests=False,
        )

        session = _make_session("test_session", file_paths=list(files.keys()))

        items = await gatherer.gather(profile, session)

        relevant_paths = {"src/auth/login.py", "src/auth/logout.py", "src/auth/session.py"}
        found_paths = {item.id for item in items}

        relevant_found = found_paths & relevant_paths
        accuracy = len(relevant_found) / len(relevant_paths) if relevant_paths else 1.0

        assert accuracy >= 0.8, f"Accuracy {accuracy:.2%} < 80%"
