"""Unit тесты для TaskAnalyzer."""

import pytest

from codelab.server.agent.context.models import TaskType
from codelab.server.agent.context.task_analyzer import LLMBasedTaskAnalyzer
from codelab.server.llm.base import LLMCapabilities
from codelab.server.llm.models import CompletionResponse, StopReason


class MockLLMForAnalyzer:
    """Mock LLM провайдер для тестирования TaskAnalyzer."""

    def __init__(self, response_text: str, *, supports_structured_output: bool = True) -> None:
        self._response_text = response_text
        self._supports_structured_output = supports_structured_output
        self.create_completion_calls = 0

    @property
    def name(self) -> str:
        return "mock"

    @property
    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(supports_structured_output=self._supports_structured_output)

    async def create_completion(self, request):
        self.create_completion_calls += 1
        return CompletionResponse(
            text=self._response_text,
            tool_calls=[],
            stop_reason=StopReason.END_TURN,
            model=request.model,
        )


@pytest.mark.asyncio
async def test_task_analyzer_llm_classification_feature():
    """Тест LLM-классификации для feature задачи."""
    response = """{
        "task_type": "feature",
        "search_terms": ["authentication", "login", "user"],
        "target_modules": ["src/auth.py"],
        "investigation_depth": 2,
        "needs_tests": true
    }"""
    llm = MockLLMForAnalyzer(response)
    analyzer = LLMBasedTaskAnalyzer(llm=llm)

    profile = await analyzer.analyze("Add user authentication", None)

    assert profile.task_type == TaskType.FEATURE
    assert "authentication" in profile.search_terms
    assert profile.investigation_depth == 2
    assert profile.needs_tests is True


@pytest.mark.asyncio
async def test_task_analyzer_llm_classification_bug_fix():
    """Тест LLM-классификации для bug fix задачи."""
    response = """{
        "task_type": "bug_fix",
        "search_terms": ["error", "crash", "exception"],
        "target_modules": ["src/handler.py"],
        "investigation_depth": 3,
        "needs_tests": true
    }"""
    llm = MockLLMForAnalyzer(response)
    analyzer = LLMBasedTaskAnalyzer(llm=llm)

    profile = await analyzer.analyze("Fix crash in request handler", None)

    assert profile.task_type == TaskType.BUG_FIX
    assert profile.investigation_depth == 3


@pytest.mark.asyncio
async def test_task_analyzer_fallback_on_llm_failure():
    """Тест fallback при отсутствии LLM."""
    analyzer = LLMBasedTaskAnalyzer(llm=None)

    profile = await analyzer.analyze("Fix bug in authentication module", None)

    assert profile.task_type == TaskType.BUG_FIX
    assert len(profile.search_terms) > 0
    assert profile.investigation_depth >= 1


@pytest.mark.asyncio
async def test_task_analyzer_skips_llm_when_structured_output_unsupported():
    """Провайдер без structured output → эвристика без холостого LLM-вызова (P2-15)."""
    llm = MockLLMForAnalyzer(
        '{"task_type": "feature", "search_terms": ["x"]}',
        supports_structured_output=False,
    )
    analyzer = LLMBasedTaskAnalyzer(llm=llm)

    profile = await analyzer.analyze("Fix bug in authentication module", None)

    assert llm.create_completion_calls == 0
    assert profile.task_type == TaskType.BUG_FIX
    assert len(profile.search_terms) > 0


@pytest.mark.asyncio
async def test_task_analyzer_calls_llm_when_structured_output_supported():
    """Провайдер с structured output → LLM-вызов выполняется."""
    llm = MockLLMForAnalyzer('{"task_type": "feature", "search_terms": ["auth"]}')
    analyzer = LLMBasedTaskAnalyzer(llm=llm)

    profile = await analyzer.analyze("Add feature", None)

    assert llm.create_completion_calls == 1
    assert profile.task_type == TaskType.FEATURE


@pytest.mark.asyncio
async def test_task_analyzer_fallback_on_invalid_json():
    """Тест fallback при невалидном JSON от LLM."""
    llm = MockLLMForAnalyzer("This is not JSON")
    analyzer = LLMBasedTaskAnalyzer(llm=llm)

    profile = await analyzer.analyze("Refactor the code", None)

    assert profile.task_type == TaskType.REFACTOR
    assert len(profile.search_terms) > 0


@pytest.mark.asyncio
async def test_task_analyzer_fallback_keywords_extraction():
    """Тест извлечения ключевых слов в fallback режиме."""
    analyzer = LLMBasedTaskAnalyzer(llm=None)

    profile = await analyzer.analyze(
        "Implement new feature for user authentication in auth.py",
        None,
    )

    assert "auth" in profile.search_terms or "authentication" in profile.search_terms
    assert "feature" in profile.search_terms or "implement" in profile.search_terms


@pytest.mark.asyncio
async def test_task_analyzer_invalid_task_type_defaults_to_feature():
    """Тест что невалидный task_type дефолтится к FEATURE."""
    response = """{
        "task_type": "invalid_type",
        "search_terms": ["test"],
        "target_modules": [],
        "investigation_depth": 1,
        "needs_tests": false
    }"""
    llm = MockLLMForAnalyzer(response)
    analyzer = LLMBasedTaskAnalyzer(llm=llm)

    profile = await analyzer.analyze("Some task", None)

    assert profile.task_type == TaskType.FEATURE


@pytest.mark.asyncio
async def test_task_analyzer_investigation_depth_clamped():
    """Тест что investigation_depth ограничивается диапазоном 1-3."""
    response = """{
        "task_type": "feature",
        "search_terms": ["test"],
        "target_modules": [],
        "investigation_depth": 10,
        "needs_tests": false
    }"""
    llm = MockLLMForAnalyzer(response)
    analyzer = LLMBasedTaskAnalyzer(llm=llm)

    profile = await analyzer.analyze("Some task", None)

    assert profile.investigation_depth == 3
