"""Тесты для моделей slash commands.

Проверяет корректность моделей AvailableCommand и AvailableCommandInput
согласно спецификации ACP Protocol 14-Slash Commands.
"""

import pytest
from pydantic import ValidationError

from codelab.server.models import AvailableCommand, AvailableCommandInput


class TestAvailableCommandInput:
    """Тесты для модели AvailableCommandInput."""

    def test_create_with_hint(self) -> None:
        """Создание input с hint."""
        input_spec = AvailableCommandInput(hint="query to search for")
        assert input_spec.hint == "query to search for"

    def test_hint_required(self) -> None:
        """hint является обязательным полем."""
        with pytest.raises(ValidationError):
            AvailableCommandInput()  # type: ignore[call-arg]

    def test_serialize_to_dict(self) -> None:
        """Сериализация в dict для JSON-RPC."""
        input_spec = AvailableCommandInput(hint="имя режима")
        data = input_spec.model_dump()
        assert data == {"hint": "имя режима"}


class TestAvailableCommand:
    """Тесты для модели AvailableCommand."""

    def test_create_minimal(self) -> None:
        """Создание команды с минимальными полями."""
        cmd = AvailableCommand(name="status", description="Show status")
        assert cmd.name == "status"
        assert cmd.description == "Show status"
        assert cmd.input is None

    def test_create_with_input(self) -> None:
        """Создание команды с input specification."""
        cmd = AvailableCommand(
            name="web",
            description="Search the web",
            input=AvailableCommandInput(hint="query to search for"),
        )
        assert cmd.name == "web"
        assert cmd.description == "Search the web"
        assert cmd.input is not None
        assert cmd.input.hint == "query to search for"

    def test_name_required(self) -> None:
        """name является обязательным полем."""
        with pytest.raises(ValidationError):
            AvailableCommand(description="Some description")  # type: ignore[call-arg]

    def test_description_required(self) -> None:
        """description является обязательным полем."""
        with pytest.raises(ValidationError):
            AvailableCommand(name="test")  # type: ignore[call-arg]

    def test_serialize_without_input(self) -> None:
        """Сериализация команды без input."""
        cmd = AvailableCommand(name="status", description="Show status")
        data = cmd.model_dump(exclude_none=True)
        assert data == {"name": "status", "description": "Show status"}

    def test_serialize_with_input(self) -> None:
        """Сериализация команды с input соответствует спецификации."""
        cmd = AvailableCommand(
            name="mode",
            description="Change mode",
            input=AvailableCommandInput(hint="mode name"),
        )
        data = cmd.model_dump()
        assert data == {
            "name": "mode",
            "description": "Change mode",
            "input": {"hint": "mode name"},
        }

    def test_extra_fields_allowed(self) -> None:
        """Дополнительные поля разрешены (extra='allow')."""
        cmd = AvailableCommand(
            name="custom",
            description="Custom command",
            custom_field="value",  # type: ignore[call-arg]
        )
        assert cmd.name == "custom"
        # extra поля доступны через model_extra
        assert "custom_field" in cmd.model_extra

    def test_from_dict(self) -> None:
        """Создание из dict (для обратной совместимости)."""
        data = {
            "name": "help",
            "description": "Show help",
            "input": {"hint": "command name"},
        }
        cmd = AvailableCommand.model_validate(data)
        assert cmd.name == "help"
        assert cmd.input is not None
        assert cmd.input.hint == "command name"


class TestAvailableCommandProtocolCompliance:
    """Тесты на соответствие спецификации ACP Protocol 14-Slash Commands."""

    def test_protocol_example_web_command(self) -> None:
        """Пример из спецификации: команда /web."""
        cmd = AvailableCommand(
            name="web",
            description="Search the web for information",
            input=AvailableCommandInput(hint="query to search for"),
        )
        data = cmd.model_dump()
        # Проверяем соответствие формату из спецификации
        assert data["name"] == "web"
        assert data["description"] == "Search the web for information"
        assert data["input"]["hint"] == "query to search for"

    def test_protocol_example_test_command(self) -> None:
        """Пример из спецификации: команда /test без input."""
        cmd = AvailableCommand(
            name="test",
            description="Run tests for the current project",
        )
        data = cmd.model_dump(exclude_none=True)
        # Команда без input не должна иметь поле input
        assert "input" not in data
        assert data["name"] == "test"

    def test_protocol_example_plan_command(self) -> None:
        """Пример из спецификации: команда /plan."""
        cmd = AvailableCommand(
            name="plan",
            description="Create a detailed implementation plan",
            input=AvailableCommandInput(hint="description of what to plan"),
        )
        data = cmd.model_dump()
        assert data["name"] == "plan"
        assert data["input"]["hint"] == "description of what to plan"
