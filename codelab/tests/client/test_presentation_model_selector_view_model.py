"""Тесты ModelSelectorViewModel."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.presentation.model_selector_view_model import (
    ModelOption,
    ModelSelectorViewModel,
)


@pytest.fixture
def mock_coordinator():
    """Создает mock SessionCoordinator для тестов."""
    coordinator = Mock()
    coordinator.set_config_option = AsyncMock()
    return coordinator


@pytest.fixture
def model_selector_vm(mock_coordinator) -> ModelSelectorViewModel:
    """Создает ModelSelectorViewModel для тестов."""
    return ModelSelectorViewModel(
        coordinator=mock_coordinator,
        event_bus=EventBus(),
        logger=None,
    )


def test_initial_state(model_selector_vm: ModelSelectorViewModel) -> None:
    """Проверяет начальное состояние ViewModel."""
    assert model_selector_vm.available_models.value == []
    assert model_selector_vm.current_model.value is None
    assert model_selector_vm.is_loading.value is False
    assert model_selector_vm.error_message.value is None
    assert model_selector_vm.is_modal_open.value is False


def test_update_models_from_config(model_selector_vm: ModelSelectorViewModel) -> None:
    """Проверяет обновление моделей из configOptions."""
    config_options = [
        {
            "id": "model",
            "name": "Model",
            "category": "model",
            "type": "select",
            "currentValue": "openai/gpt-4o",
            "options": [
                {
                    "value": "openai/gpt-4o",
                    "name": "gpt-4o",
                    "description": "128,000 context",
                    "_pricing": "$0.000005/input",
                },
                {
                    "value": "anthropic/claude-sonnet-4",
                    "name": "claude-sonnet-4",
                    "description": "200,000 context",
                    "_pricing": "$0.000003/input",
                },
            ],
        }
    ]

    model_selector_vm.update_models_from_config(config_options)

    assert len(model_selector_vm.available_models.value) == 2
    assert model_selector_vm.current_model.value == "openai/gpt-4o"

    first_model = model_selector_vm.available_models.value[0]
    assert first_model.value == "openai/gpt-4o"
    assert first_model.label == "gpt-4o"
    assert first_model.description == "128,000 context"
    assert first_model.pricing == "$0.000005/input"
    assert first_model.provider_id == "openai"
    assert first_model.model_id == "gpt-4o"


def test_update_current_model(model_selector_vm: ModelSelectorViewModel) -> None:
    """Проверяет прямое обновление текущей модели."""
    model_selector_vm.update_current_model("anthropic/claude-sonnet-4")
    assert model_selector_vm.current_model.value == "anthropic/claude-sonnet-4"


def test_get_current_model_label_no_model(model_selector_vm: ModelSelectorViewModel) -> None:
    """Проверяет получение label когда модель не выбрана."""
    assert model_selector_vm.get_current_model_label() == "Не выбрано"


def test_get_current_model_label_from_list(model_selector_vm: ModelSelectorViewModel) -> None:
    """Проверяет получение label из списка моделей."""
    config_options = [
        {
            "id": "model",
            "category": "model",
            "type": "select",
            "currentValue": "openai/gpt-4o",
            "options": [
                {"value": "openai/gpt-4o", "name": "gpt-4o"},
            ],
        }
    ]
    model_selector_vm.update_models_from_config(config_options)
    assert model_selector_vm.get_current_model_label() == "gpt-4o"


def test_get_current_model_label_fallback(model_selector_vm: ModelSelectorViewModel) -> None:
    """Проверяет fallback получения label из value."""
    model_selector_vm.update_current_model("openai/gpt-4o")
    assert model_selector_vm.get_current_model_label() == "gpt-4o"


@pytest.mark.asyncio
async def test_select_model_success(
    model_selector_vm: ModelSelectorViewModel,
    mock_coordinator: Mock,
) -> None:
    """Проверяет успешный выбор модели."""
    config_options = [
        {
            "id": "model",
            "category": "model",
            "type": "select",
            "currentValue": "openai/gpt-4o",
            "options": [
                {"value": "openai/gpt-4o", "name": "gpt-4o"},
                {"value": "anthropic/claude-sonnet-4", "name": "claude-sonnet-4"},
            ],
        }
    ]
    model_selector_vm.update_models_from_config(config_options)

    # Результат с обновлённой моделью
    updated_config_options = [
        {
            "id": "model",
            "category": "model",
            "type": "select",
            "currentValue": "anthropic/claude-sonnet-4",
            "options": [
                {"value": "openai/gpt-4o", "name": "gpt-4o"},
                {"value": "anthropic/claude-sonnet-4", "name": "claude-sonnet-4"},
            ],
        }
    ]
    mock_coordinator.set_config_option.return_value = {
        "configOptions": updated_config_options
    }

    await model_selector_vm.select_model_cmd.execute(
        session_id="sess_1",
        model_value="anthropic/claude-sonnet-4",
    )

    assert model_selector_vm.current_model.value == "anthropic/claude-sonnet-4"
    mock_coordinator.set_config_option.assert_called_once_with(
        session_id="sess_1",
        config_id="model",
        value="anthropic/claude-sonnet-4",
    )


@pytest.mark.asyncio
async def test_select_model_no_session(
    model_selector_vm: ModelSelectorViewModel,
    mock_coordinator: Mock,
) -> None:
    """Проверяет выбор модели без активной сессии."""
    await model_selector_vm.select_model_cmd.execute(
        session_id="",
        model_value="openai/gpt-4o",
    )

    mock_coordinator.set_config_option.assert_not_called()


@pytest.mark.asyncio
async def test_select_model_not_available(model_selector_vm: ModelSelectorViewModel) -> None:
    """Проверяет выбор недоступной модели."""
    with pytest.raises(ValueError, match="Model.*is not available"):
        await model_selector_vm.select_model_cmd.execute(
            session_id="sess_1",
            model_value="unknown/model",
        )


def test_parse_model_options_empty(model_selector_vm: ModelSelectorViewModel) -> None:
    """Проверяет парсинг пустого списка options."""
    result = model_selector_vm._parse_model_options([])
    assert result == []


def test_parse_model_options_invalid(model_selector_vm: ModelSelectorViewModel) -> None:
    """Проверяет парсинг некорректных options."""
    raw_options = [
        "not a dict",
        {"no_value": "key"},
        {"value": "", "label": "empty"},
        {"value": "openai/gpt-4o", "label": "gpt-4o"},
    ]
    result = model_selector_vm._parse_model_options(raw_options)
    assert len(result) == 1
    assert result[0].value == "openai/gpt-4o"


def test_model_option_properties() -> None:
    """Проверяет свойства ModelOption."""
    model = ModelOption(
        value="openai/gpt-4o",
        label="gpt-4o",
        description="128k context",
        pricing="$0.000005/input",
    )
    assert model.provider_id == "openai"
    assert model.model_id == "gpt-4o"


def test_model_option_no_slash() -> None:
    """Проверяет ModelOption без slash в value."""
    model = ModelOption(value="local-model", label="Local")
    assert model.provider_id == ""
    assert model.model_id == "local-model"
