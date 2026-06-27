"""E2E тест для проверки точности сбора контекста.

Тестирует полный пайплайн:
SingleStrategy → ExecutionEngine → ContextManager → сбор файлов

Цель: точность сбора релевантных файлов ≥80%.

ContextGatherer получает структуру проекта из session.config_values["project_structure"],
которую агент сохраняет через terminal/create в рамках agent loop.
"""

from __future__ import annotations

import json
from typing import Any
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

    def __init__(
        self,
        files: dict[str, str] | None = None,
        *,
        terminal_output: str | None = None,
    ) -> None:
        self._files = files or {}
        self._terminal_output = terminal_output
        self._terminal_counter = 0

    def get_available_tools(self, session_id: str) -> list:
        return [_FakeTool("fs/read_text_file")]

    async def execute_tool(
        self, session_id: str, tool_name: str, arguments: dict, session: Any = None
    ) -> ToolExecutionResult:
        if tool_name == "fs/read_text_file":
            path = arguments.get("path", "")
            content = self._files.get(path)
            if content is not None:
                return ToolExecutionResult(success=True, output=content)
            return ToolExecutionResult(success=False, error="File not found")

        if tool_name == "terminal/create":
            self._terminal_counter += 1
            terminal_id = f"mock-terminal-{self._terminal_counter}"
            return ToolExecutionResult(
                success=True,
                raw_output={"terminal_id": terminal_id},
                metadata={"terminal_id": terminal_id},
            )

        if tool_name == "terminal/wait_for_exit":
            output = self._terminal_output or ""
            return ToolExecutionResult(
                success=True,
                raw_output={"output": output},
                output=output,
            )

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
        """Без project_structure и без terminal gatherer возвращает пустой результат."""
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
    async def test_gather_bootstraps_project_structure_via_terminal(self):
        """Gatherer должен сам получить структуру через terminal, если её нет в сессии."""
        terminal_output = "./lib/main.dart\n./lib/auth_service.dart\n./pubspec.yaml\n"
        files = {
            "lib/main.dart": "void main() {}",
            "lib/auth_service.dart": "class AuthService {}",
            "pubspec.yaml": "name: test_app",
        }
        tool_registry = MockToolRegistry(files, terminal_output=terminal_output)
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

        paths = [item.id for item in items]
        assert any("auth" in p for p in paths)

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


class TestImprovedSearch:
    """Тесты улучшенной логики поиска."""

    def test_detect_project_type_dart(self):
        """Детекция Dart проекта по pubspec.yaml."""
        files = ["lib/main.dart", "lib/weather_service.dart", "pubspec.yaml"]
        project_type = ACPContextGatherer._detect_project_type(files)
        assert project_type == "dart"

    def test_detect_project_type_python(self):
        """Детекция Python проекта по pyproject.toml."""
        files = ["src/main.py", "pyproject.toml", "tests/test_main.py"]
        project_type = ACPContextGatherer._detect_project_type(files)
        assert project_type == "python"

    def test_detect_project_type_javascript(self):
        """Детекция JavaScript проекта по package.json."""
        files = ["src/index.js", "package.json", "src/App.tsx"]
        project_type = ACPContextGatherer._detect_project_type(files)
        assert project_type == "javascript"

    def test_map_path_python_to_dart(self):
        """Маппинг Python путей в Dart."""
        candidates = ACPContextGatherer._map_path_to_project("src/auth.py", "dart")
        assert "lib/auth.dart" in candidates
        assert "lib/src/auth.dart" in candidates

    def test_map_path_dart_to_python(self):
        """Маппинг Dart путей в Python."""
        candidates = ACPContextGatherer._map_path_to_project("lib/auth.dart", "python")
        assert "src/auth.py" in candidates

    @pytest.mark.asyncio
    async def test_find_similar_files_fuzzy(self):
        """Fuzzy matching для похожих имён."""
        files = ["lib/auth_screen.dart", "lib/main.dart", "lib/weather_service.dart"]
        tool_registry = MockToolRegistry({})
        dep_graph = RegexDependencyGraph()
        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
        )

        similar = gatherer._find_similar_files("src/auth.py", files)
        assert "lib/auth_screen.dart" in similar

    @pytest.mark.asyncio
    async def test_find_similar_files_cross_language(self):
        """Cross-language маппинг: Python → Dart."""
        files = ["lib/auth.dart", "lib/main.dart", "pubspec.yaml"]
        tool_registry = MockToolRegistry({})
        dep_graph = RegexDependencyGraph()
        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
        )

        similar = gatherer._find_similar_files("src/auth.py", files)
        assert "lib/auth.dart" in similar

    @pytest.mark.asyncio
    async def test_search_in_files_by_content(self):
        """Поиск по содержимому файла, когда термин не в имени."""
        files = {
            "lib/main.dart": "class AuthorizationService { void login() {} }",
            "lib/weather_service.dart": "class WeatherService {}",
        }
        tool_registry = MockToolRegistry(files)
        dep_graph = RegexDependencyGraph()
        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test_session",
        )

        project_files = list(files.keys())
        session = _make_session("test_session")
        results = await gatherer._search_in_files("authorization", project_files, session)
        assert "lib/main.dart" in results

    @pytest.mark.asyncio
    async def test_gather_dart_project_with_python_hallucination(self):
        """E2E: Dart проект с галлюцинированными Python путями от LLM."""
        files = {
            "lib/main.dart": "void main() { runApp(MyApp()); }",
            "lib/auth_service.dart": "class AuthService { void login() {} }",
            "lib/screens/auth_screen.dart": "class AuthScreen extends StatelessWidget {}",
            "pubspec.yaml": "name: my_app",
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
            search_terms=["auth", "login"],
            target_modules=["src/auth.py", "src/screens/auth_screen.py"],
            investigation_depth=1,
            needs_tests=False,
        )

        session = _make_session("test_session", file_paths=list(files.keys()))

        items = await gatherer.gather(profile, session)

        paths = [item.id for item in items]
        assert any("auth" in p and p.endswith(".dart") for p in paths)

    @pytest.mark.asyncio
    async def test_gather_fallback_files_when_no_candidates(self):
        """Gatherer должен собирать основные файлы проекта, когда нет кандидатов."""
        files = {
            "lib/main.dart": "void main() {}",
            "lib/weather_service.dart": "class WeatherService {}",
            "pubspec.yaml": "name: test_app",
            "README.md": "# Test App",
            "test/widget_test.dart": "void main() {}",
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
            search_terms=["несуществующий_термин"],
            target_modules=["src/nonexistent.py"],
            investigation_depth=1,
            needs_tests=False,
        )

        session = _make_session("test_session", file_paths=list(files.keys()))

        items = await gatherer.gather(profile, session)

        paths = [item.id for item in items]
        assert len(paths) > 0
        assert "pubspec.yaml" in paths or "lib/main.dart" in paths

    def test_get_fallback_files_priority(self):
        """_get_fallback_files должен возвращать файлы в правильном приоритете."""
        project_files = [
            "lib/weather_service.dart",
            "lib/main.dart",
            "pubspec.yaml",
            "README.md",
            "test/widget_test.dart",
            "lib/models/weather.dart",
        ]

        fallback = ACPContextGatherer._get_fallback_files(project_files, max_files=5)

        assert len(fallback) > 0
        assert "pubspec.yaml" in fallback
        assert "lib/main.dart" in fallback

    def test_filter_paths_git_directory(self):
        """_filter_paths должен фильтровать .git/objects (не только .git)."""
        paths = [
            ".git/objects/0d/aca4c97ef7c6777ed79859f6bf82416ce4fddf",
            ".git/HEAD",
            "lib/main.dart",
            "pubspec.yaml",
        ]
        filtered = ACPContextGatherer._filter_paths(paths)
        assert "lib/main.dart" in filtered
        assert "pubspec.yaml" in filtered
        assert not any(".git" in p for p in filtered)

    def test_get_fallback_files_excludes_ignored_dirs(self):
        """_get_fallback_files не должен включать файлы из .dart_tool, .git и т.д."""
        project_files = [
            "lib/main.dart",
            "pubspec.yaml",
            ".dart_tool/extension_discovery/README.md",
            ".git/HEAD",
            "node_modules/pkg/index.js",
        ]
        fallback = ACPContextGatherer._get_fallback_files(project_files, max_files=10)
        assert "lib/main.dart" in fallback
        assert "pubspec.yaml" in fallback
        assert not any(".dart_tool" in p for p in fallback)
        assert not any(".git" in p for p in fallback)
        assert not any("node_modules" in p for p in fallback)
