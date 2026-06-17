"""Тесты для компонента PromptInput с MVVM интеграцией."""

from __future__ import annotations

import pytest
from textual.app import App

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.presentation.chat_view_model import ChatViewModel
from codelab.client.tui.components.prompt_input import PromptInput


@pytest.fixture
def event_bus() -> EventBus:
    """Создать EventBus для тестов."""
    return EventBus()


@pytest.fixture
def chat_view_model(event_bus: EventBus) -> ChatViewModel:
    """Создать ChatViewModel для тестов."""
    coordinator = None
    return ChatViewModel(coordinator=coordinator, event_bus=event_bus, logger=None)


@pytest.fixture
def prompt_input(chat_view_model: ChatViewModel) -> PromptInput:
    """Создать PromptInput с ChatViewModel."""
    return PromptInput(chat_view_model)


def test_prompt_input_initializes_with_chat_view_model(chat_view_model: ChatViewModel) -> None:
    """Проверить что PromptInput инициализируется с ChatViewModel."""
    prompt_input = PromptInput(chat_view_model)
    
    assert prompt_input.chat_vm is chat_view_model
    assert prompt_input.id == "prompt-input"


def test_prompt_input_is_enabled_by_default(prompt_input: PromptInput) -> None:
    """Проверить что PromptInput включен по умолчанию."""
    assert prompt_input.disabled is False


async def test_prompt_input_disables_when_streaming(
    chat_view_model: ChatViewModel,
) -> None:
    """Проверить что PromptInput отключается при streaming."""

    class TestApp(App):
        pass

    app = TestApp()
    async with app.run_test() as pilot:
        prompt_input = PromptInput(chat_view_model)
        await pilot.app.mount(prompt_input)
        await pilot.pause()

        chat_view_model.is_streaming.value = True
        await pilot.pause()

        assert prompt_input._text_area is not None
        assert prompt_input._text_area.disabled is True


async def test_prompt_input_enables_when_streaming_done(
    chat_view_model: ChatViewModel,
) -> None:
    """Проверить что PromptInput включается когда streaming заканчивается."""

    class TestApp(App):
        pass

    app = TestApp()
    async with app.run_test() as pilot:
        prompt_input = PromptInput(chat_view_model)
        await pilot.app.mount(prompt_input)
        await pilot.pause()

        # Сначала включить streaming
        chat_view_model.is_streaming.value = True
        await pilot.pause()
        assert prompt_input._text_area is not None
        assert prompt_input._text_area.disabled is True

        # Потом отключить
        chat_view_model.is_streaming.value = False
        await pilot.pause()
        assert prompt_input._text_area.disabled is False



