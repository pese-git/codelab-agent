"""Тесты для /strategy slash command handler."""

from unittest.mock import MagicMock

from codelab.server.protocol.handlers.slash_commands.builtin.strategy import (
    StrategyCommandHandler,
)


class TestStrategyCommandHandlerExecute:
    """Тесты для execute()."""

    def _create_handler(
        self,
        current_strategy: str = "single",
        available_strategies: list[str] | None = None,
    ) -> StrategyCommandHandler:
        """Создать handler с mocked dispatcher."""
        dispatcher = MagicMock()
        dispatcher.get_strategy.return_value = current_strategy
        dispatcher.get_available_strategies.return_value = (
            available_strategies or ["single", "hierarchical"]
        )
        dispatcher.set_current_strategy.return_value = True
        return StrategyCommandHandler(strategy_dispatcher=dispatcher)

    def test_show_current_strategy_no_args(self) -> None:
        """Без аргументов показывает текущую strategy."""
        handler = self._create_handler(current_strategy="single")

        session = MagicMock()
        result = handler.execute([], session)

        assert result is not None
        content = result.content[0]["text"]
        assert "single" in content
        assert "Доступные strategies" in content

    def test_show_current_strategy_with_marker(self) -> None:
        """Текущая strategy отмечена маркером →."""
        handler = self._create_handler(
            current_strategy="hierarchical",
            available_strategies=["single", "hierarchical"],
        )

        session = MagicMock()
        result = handler.execute([], session)

        content = result.content[0]["text"]
        assert "→ `hierarchical`" in content
        assert " `single`" in content

    def test_set_new_strategy(self) -> None:
        """Установка новой strategy."""
        handler = self._create_handler(current_strategy="single")

        session = MagicMock()
        session.config_values = {}
        result = handler.execute(["hierarchical"], session)

        content = result.content[0]["text"]
        assert "single" in content
        assert "hierarchical" in content
        assert session.config_values["_active_strategy"] == "hierarchical"

    def test_set_same_strategy(self) -> None:
        """Установка той же strategy — информационное сообщение."""
        handler = self._create_handler(current_strategy="single")

        session = MagicMock()
        session.config_values = {}
        result = handler.execute(["single"], session)

        content = result.content[0]["text"]
        assert "уже активна" in content
        assert "_active_strategy" not in session.config_values

    def test_set_unknown_strategy(self) -> None:
        """Установка неизвестной strategy — ошибка."""
        handler = self._create_handler(
            current_strategy="single",
            available_strategies=["single", "hierarchical"],
        )

        session = MagicMock()
        session.config_values = {}
        result = handler.execute(["unknown"], session)

        content = result.content[0]["text"]
        assert "недоступна" in content
        assert "single" in content
        assert "hierarchical" in content
        assert "_active_strategy" not in session.config_values

    def test_set_strategy_dispatcher_fails(self) -> None:
        """Dispatcher не может установить strategy — ошибка."""
        handler = self._create_handler(current_strategy="single")
        handler._strategy_dispatcher.set_current_strategy.return_value = False

        session = MagicMock()
        session.config_values = {}
        result = handler.execute(["hierarchical"], session)

        content = result.content[0]["text"]
        assert "Не удалось установить" in content
        assert "_active_strategy" not in session.config_values

    def test_case_insensitive_strategy_name(self) -> None:
        """Имя strategy регистронезависимое."""
        handler = self._create_handler(current_strategy="single")

        session = MagicMock()
        session.config_values = {}
        result = handler.execute(["HIERARCHICAL"], session)

        content = result.content[0]["text"]
        assert "hierarchical" in content
        assert session.config_values["_active_strategy"] == "hierarchical"


class TestStrategyCommandHandlerDefinition:
    """Тесты для get_definition()."""

    def _create_handler(
        self,
        current_strategy: str = "single",
        available_strategies: list[str] | None = None,
    ) -> StrategyCommandHandler:
        """Создать handler с mocked dispatcher."""
        dispatcher = MagicMock()
        dispatcher.get_strategy.return_value = current_strategy
        dispatcher.get_available_strategies.return_value = (
            available_strategies or ["single", "hierarchical"]
        )
        dispatcher.set_current_strategy.return_value = True
        return StrategyCommandHandler(strategy_dispatcher=dispatcher)

    def test_get_definition_returns_available_command(self) -> None:
        """get_definition возвращает AvailableCommand."""
        handler = self._create_handler(
            available_strategies=["single", "hierarchical"],
        )

        definition = handler.get_definition()

        assert definition.name == "strategy"
        assert "execution strategy" in definition.description
        assert definition.input is not None
        assert "single" in definition.input.hint
        assert "hierarchical" in definition.input.hint

    def test_get_definition_with_empty_strategies(self) -> None:
        """get_definition с пустым списком strategies."""
        handler = self._create_handler(available_strategies=[])

        definition = handler.get_definition()

        assert definition.name == "strategy"
        assert definition.input is not None
