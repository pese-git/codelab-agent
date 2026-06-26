"""Unit тесты для TokenBudgetManager."""


from codelab.server.agent.context.budget import DefaultTokenBudgetManager
from codelab.server.agent.context.models import ContextConfig


def test_budget_manager_allocate_default_shares():
    """Тест распределения бюджета с долями по умолчанию."""
    manager = DefaultTokenBudgetManager()

    allocation = manager.allocate(10000)

    assert allocation.system_tokens == 2000
    assert allocation.history_tokens == 5000
    assert allocation.tool_output_tokens == 2000
    assert allocation.response_buffer_tokens == 1000
    total = (
        allocation.system_tokens
        + allocation.history_tokens
        + allocation.tool_output_tokens
        + allocation.response_buffer_tokens
    )
    assert total == 10000


def test_budget_manager_allocate_custom_shares():
    """Тест распределения бюджета с кастомными долями."""
    config = ContextConfig(
        system_share=0.3,
        history_share=0.4,
        tool_output_share=0.2,
        response_buffer_share=0.1,
    )
    manager = DefaultTokenBudgetManager(config)

    allocation = manager.allocate(10000)

    assert allocation.system_tokens == 3000
    assert allocation.history_tokens == 4000
    assert allocation.tool_output_tokens == 2000
    assert allocation.response_buffer_tokens == 1000


def test_budget_manager_bound_content_no_truncation():
    """Тест что короткий контент не обрезается."""
    manager = DefaultTokenBudgetManager()
    content = "Short content"

    result = manager.bound_content(content, max_tokens=1000)

    assert result == content


def test_budget_manager_bound_content_truncation():
    """Тест обрезки длинного контента."""
    manager = DefaultTokenBudgetManager()
    content = "x" * 10000

    result = manager.bound_content(content, max_tokens=100)

    assert len(result) < len(content)
    assert "truncated" in result


def test_budget_manager_bound_content_preserves_head_and_tail():
    """Тест что обрезка сохраняет начало и конец."""
    manager = DefaultTokenBudgetManager()
    content = "HEAD" + "x" * 10000 + "TAIL"

    result = manager.bound_content(content, max_tokens=100)

    assert result.startswith("HEAD")
    assert result.endswith("TAIL")


def test_budget_manager_estimate_tokens():
    """Тест приближённой оценки токенов."""
    text = "This is a test string with some words"

    tokens = DefaultTokenBudgetManager.estimate_tokens(text)

    expected = len(text) // 4
    assert tokens == expected


def test_budget_manager_allocate_very_small_budget():
    """Тест распределения очень маленького бюджета."""
    manager = DefaultTokenBudgetManager()

    allocation = manager.allocate(100)

    assert allocation.system_tokens >= 0
    assert allocation.history_tokens >= 0
    assert allocation.tool_output_tokens >= 0
    assert allocation.response_buffer_tokens >= 0


def test_budget_manager_bound_content_very_small_limit():
    """Тест обрезки с очень маленьким лимитом."""
    manager = DefaultTokenBudgetManager()
    content = "Some content here"

    result = manager.bound_content(content, max_tokens=1)

    assert len(result) <= 4
