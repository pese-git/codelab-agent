"""TaskAnalyzer — LLM-классификация задач для сбора контекста.

Анализирует промпт пользователя и определяет:
- Тип задачи (bug_fix/feature/refactor/architecture)
- Поисковые термины для поиска релевантных файлов
- Целевые модули
- Глубину исследования (1-3)
- Необходимость тестов

Слой A — Сбор контекста (Phase 1).
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from codelab.server.agent.context.interfaces import TaskAnalyzer
from codelab.server.agent.context.models import TaskProfile, TaskType
from codelab.server.llm.models import CompletionRequest, LLMMessage

if TYPE_CHECKING:
    from codelab.server.llm.base import LLMProvider

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """Analyze the following user task and extract structured
information for context gathering.

User task:
{prompt}

Return a JSON object with the following fields:
- task_type: one of "bug_fix", "feature", "refactor", "architecture"
- search_terms: list of 3-7 key terms for searching relevant files
  (module names, function names, error messages, etc.)
- target_modules: list of 1-5 likely target modules/files
  (e.g., ["src/auth.py", "src/models/user.py"])
- investigation_depth: integer 1-3
  (1=simple lookup, 2=moderate exploration, 3=deep investigation)
- needs_tests: boolean indicating if tests should be written/updated

Return ONLY valid JSON, no additional text."""


class LLMBasedTaskAnalyzer(TaskAnalyzer):
    """TaskAnalyzer с LLM-классификацией и fallback."""

    def __init__(
        self,
        llm: LLMProvider | None = None,
        model: str = "openai/gpt-4o-mini",
    ) -> None:
        self._llm = llm
        self._model = model

    async def analyze(self, prompt: str, session: object) -> TaskProfile:
        """Классифицировать задачу и извлечь стратегию сбора.

        Args:
            prompt: Текст промпта пользователя
            session: Состояние сессии (не используется в Phase 1)

        Returns:
            TaskProfile с классификацией и стратегией поиска
        """
        if self._llm is None:
            logger.debug("LLM not available, using fallback classification")
            return self._fallback_classify(prompt)

        try:
            return await self._llm_classify(prompt)
        except Exception:
            logger.exception("LLM classification failed, using fallback")
            return self._fallback_classify(prompt)

    async def _llm_classify(self, prompt: str) -> TaskProfile:
        """LLM-классификация с парсингом JSON ответа."""
        assert self._llm is not None

        formatted_prompt = CLASSIFICATION_PROMPT.format(prompt=prompt)

        request = CompletionRequest(
            model=self._model,
            messages=[LLMMessage(role="user", content=formatted_prompt)],
            temperature=0.0,
            max_tokens=500,
        )

        response = await self._llm.create_completion(request)
        text = response.text.strip()

        return self._parse_classification(text, prompt)

    def _parse_classification(self, text: str, original_prompt: str) -> TaskProfile:
        """Парсить JSON ответ LLM в TaskProfile."""
        json_match = re.search(r"\{[\s\S]*\}", text)
        if not json_match:
            logger.warning("No JSON found in LLM response, using fallback")
            return self._fallback_classify(original_prompt)

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in LLM response, using fallback")
            return self._fallback_classify(original_prompt)

        task_type_str = data.get("task_type", "feature")
        try:
            task_type = TaskType(task_type_str)
        except ValueError:
            logger.warning("Invalid task_type '%s', defaulting to FEATURE", task_type_str)
            task_type = TaskType.FEATURE

        search_terms = data.get("search_terms", [])
        if not isinstance(search_terms, list):
            search_terms = []
        search_terms = [str(t) for t in search_terms if t]

        target_modules = data.get("target_modules", [])
        if not isinstance(target_modules, list):
            target_modules = []
        target_modules = [str(m) for m in target_modules if m]

        investigation_depth = data.get("investigation_depth", 1)
        if not isinstance(investigation_depth, int) or investigation_depth < 1:
            investigation_depth = 1
        elif investigation_depth > 3:
            investigation_depth = 3

        needs_tests = data.get("needs_tests", False)
        if not isinstance(needs_tests, bool):
            needs_tests = bool(needs_tests)

        if not search_terms:
            search_terms = self._extract_keywords(original_prompt)

        return TaskProfile(
            task_type=task_type,
            search_terms=search_terms,
            target_modules=target_modules,
            investigation_depth=investigation_depth,
            needs_tests=needs_tests,
        )

    def _fallback_classify(self, prompt: str) -> TaskProfile:
        """Эвристическая классификация без LLM."""
        prompt_lower = prompt.lower()

        bug_keywords = ["bug", "error", "fix", "issue", "crash", "broken"]
        refactor_keywords = ["refactor", "clean", "restructure", "improve"]
        arch_keywords = ["architecture", "design", "pattern", "structure"]

        if any(word in prompt_lower for word in bug_keywords):
            task_type = TaskType.BUG_FIX
        elif any(word in prompt_lower for word in refactor_keywords):
            task_type = TaskType.REFACTOR
        elif any(word in prompt_lower for word in arch_keywords):
            task_type = TaskType.ARCHITECTURE
        else:
            task_type = TaskType.FEATURE

        search_terms = self._extract_keywords(prompt)

        target_modules = []
        file_pattern = re.compile(r"[a-zA-Z0-9_/\\.-]+\.(py|js|ts|tsx|jsx)")
        matches = file_pattern.findall(prompt)
        for match in matches[:5]:
            if match not in target_modules:
                target_modules.append(match)

        investigation_depth = 2 if len(search_terms) > 3 else 1

        needs_tests = any(word in prompt_lower for word in ["test", "spec", "coverage"])

        return TaskProfile(
            task_type=task_type,
            search_terms=search_terms,
            target_modules=target_modules,
            investigation_depth=investigation_depth,
            needs_tests=needs_tests,
        )

    @staticmethod
    def _extract_keywords(prompt: str) -> list[str]:
        """Извлечь ключевые слова из промпта."""
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", prompt)

        stop_words = {
            "the", "and", "for", "with", "that", "this", "from", "have", "was",
            "are", "been", "will", "can", "should", "would", "could", "might",
            "must", "need", "want", "like", "just", "about", "into", "your",
            "you", "our", "their", "its", "some", "any", "all", "each",
        }

        keywords = [w.lower() for w in words if w.lower() not in stop_words]

        unique = []
        seen = set()
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)

        return unique[:7]
