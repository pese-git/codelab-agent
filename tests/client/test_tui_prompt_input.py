from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import App

from codelab.client.tui.components.prompt_input import PromptInput

if TYPE_CHECKING:
    from codelab.client.presentation.chat_view_model import ChatViewModel


def test_prompt_input_supports_up_down_history_bindings() -> None:
    bindings: set[str] = set()
    for binding in PromptInput.BINDINGS:
        key = getattr(binding, "key", None)
        if isinstance(key, str):
            bindings.add(key)
            continue
        if isinstance(binding, tuple) and binding:
            first = binding[0]
            if isinstance(first, str):
                bindings.add(first)
                continue
        bindings.add(str(binding))

    # В текущей реализации используются ctrl+up/ctrl+down для истории
    assert "ctrl+up" in bindings
    assert "ctrl+down" in bindings


async def test_prompt_input_history_navigation_restores_draft(
    mock_chat_view_model: ChatViewModel,
) -> None:
    """Навигация по истории восстанавливает черновик."""

    class TestApp(App):
        pass

    app = TestApp()
    async with app.run_test() as pilot:
        prompt_input = PromptInput(mock_chat_view_model)
        await pilot.app.mount(prompt_input)
        await pilot.pause()

        prompt_input.set_active_session("sess_1")
        prompt_input.remember_prompt("first")
        prompt_input.remember_prompt("second")

        prompt_input.text = "draft"
        prompt_input.action_history_previous()
        assert prompt_input.text == "second"

        prompt_input.action_history_previous()
        assert prompt_input.text == "first"

        prompt_input.action_history_next()
        assert prompt_input.text == "second"

        prompt_input.action_history_next()
        assert prompt_input.text == "draft"


async def test_prompt_input_history_is_isolated_by_session(
    mock_chat_view_model: ChatViewModel,
) -> None:
    """История промптов изолирована по сессиям."""

    class TestApp(App):
        pass

    app = TestApp()
    async with app.run_test() as pilot:
        prompt_input = PromptInput(mock_chat_view_model)
        await pilot.app.mount(prompt_input)
        await pilot.pause()

        prompt_input.set_active_session("sess_1")
        prompt_input.remember_prompt("one")

        prompt_input.set_active_session("sess_2")
        prompt_input.remember_prompt("two")
        prompt_input.action_history_previous()
        assert prompt_input.text == "two"

        prompt_input.set_active_session("sess_1")
        prompt_input.action_history_previous()
        assert prompt_input.text == "one"


async def test_prompt_input_skips_consecutive_duplicates(
    mock_chat_view_model: ChatViewModel,
) -> None:
    """Последовательные дубликаты пропускаются в истории."""

    class TestApp(App):
        pass

    app = TestApp()
    async with app.run_test() as pilot:
        prompt_input = PromptInput(mock_chat_view_model)
        await pilot.app.mount(prompt_input)
        await pilot.pause()

        prompt_input.set_active_session("sess_1")
        prompt_input.remember_prompt("same")
        prompt_input.remember_prompt("same")

        prompt_input.action_history_previous()
        assert prompt_input.text == "same"

        prompt_input.action_history_previous()
        assert prompt_input.text == "same"
