"""ConfigOptionSelectorViewModel для управления выбором config option.

Универсальный ViewModel для выбора любой config option из configOptions:
- model (LLM модель)
- mode (режим сессии: ask/code)
- _agent (агент)
- _active_strategy (стратегия выполнения)

Отвечает за:
- Хранение списка доступных options из configOptions
- Текущее выбранное значение
- Отправку запросов на смену значения через coordinator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codelab.client.presentation.base_view_model import BaseViewModel
from codelab.client.presentation.observable import Observable, ObservableCommand


@dataclass
class ConfigOption:
    """Опция конфигурации для выбора.

    Attributes:
        value: Уникальный идентификатор (например, "openai/gpt-4o", "single")
        label: Отображаемое имя (например, "GPT-4o", "Single")
        description: Описание опции (опционально)
        extra: Дополнительные данные (pricing, provider_id и т.д.)
    """

    value: str
    label: str
    description: str = ""
    extra: dict[str, str] = field(default_factory=dict)


class ConfigOptionSelectorViewModel(BaseViewModel):
    """Универсальный ViewModel для выбора config option.

    Конфигурируется через config_id и может использоваться для:
    - model: выбор LLM модели
    - mode: выбор режима сессии
    - _agent: выбор агента
    - _active_strategy: выбор стратегии выполнения

    Пример использования:
        >>> # Для выбора модели
        >>> model_vm = ConfigOptionSelectorViewModel(
        ...     config_id="model",
        ...     title="Модель",
        ...     coordinator=coordinator,
        ... )
        >>> model_vm.update_from_config(config_options, session_id)
        >>> await model_vm.select_option_cmd.execute(session_id, "openai/gpt-4o")

        >>> # Для выбора стратегии
        >>> strategy_vm = ConfigOptionSelectorViewModel(
        ...     config_id="_active_strategy",
        ...     title="Стратегия",
        ...     coordinator=coordinator,
        ... )
    """

    def __init__(
        self,
        config_id: str,
        title: str,
        coordinator: Any,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        """Инициализировать ConfigOptionSelectorViewModel.

        Args:
            config_id: ID config option ("model", "mode", "_agent", "_active_strategy")
            title: Заголовок для UI (например, "Модель", "Стратегия")
            coordinator: SessionCoordinator для работы с сервером
            event_bus: EventBus для публикации/подписки на события
            logger: Logger для логирования
        """
        super().__init__(event_bus, logger)
        self._config_id = config_id
        self._title = title
        self.coordinator = coordinator

        # Observable свойства
        self.available_options: Observable[list[ConfigOption]] = Observable([])
        self.current_value: Observable[str | None] = Observable(None)
        self.is_loading: Observable[bool] = Observable(False)
        self.error_message: Observable[str | None] = Observable(None)
        self.is_modal_open: Observable[bool] = Observable(False)

        # Кэш configOptions по session_id
        self._config_cache: dict[str, dict[str, Any]] = {}

        # Observable команды
        self.select_option_cmd = ObservableCommand(self._select_option)
        self.open_modal_cmd = ObservableCommand(self._open_modal)
        self.close_modal_cmd = ObservableCommand(self._close_modal)

    @property
    def config_id(self) -> str:
        """ID config option."""
        return self._config_id

    @property
    def title(self) -> str:
        """Заголовок для UI."""
        return self._title

    def update_from_config(
        self,
        config_options: list[dict[str, Any]],
        session_id: str | None = None,
    ) -> None:
        """Обновить список options из configOptions.

        Ищет config option с id=config_id и извлекает options.

        Args:
            config_options: Список config options от сервера
            session_id: ID сессии для кэширования (опционально)
        """
        # Кэшируем все config options
        if session_id:
            self._config_cache[session_id] = {
                opt["id"]: opt for opt in config_options if "id" in opt
            }

        # Ищем нужный config option
        target_config = None
        for option in config_options:
            if option.get("id") == self._config_id:
                target_config = option
                break

        if target_config is None:
            self.logger.debug(
                "config_option_not_found",
                config_id=self._config_id,
            )
            return

        # Извлекаем текущее значение
        current = target_config.get("currentValue") or target_config.get("default")
        if current:
            self.current_value.value = current

        # Извлекаем список options
        raw_options = target_config.get("options", [])
        options = self._parse_options(raw_options)

        self.available_options.value = options
        self.logger.info(
            "config_options_updated",
            config_id=self._config_id,
            option_count=len(options),
            current_value=current,
        )

    def update_current_value(self, value: str) -> None:
        """Обновить текущее значение напрямую.

        Args:
            value: Новое значение
        """
        self.current_value.value = value
        self.logger.debug(
            "current_value_updated",
            config_id=self._config_id,
            value=value,
        )

    def get_current_label(self) -> str:
        """Получить отображаемое имя текущего значения.

        Returns:
            Отображаемое имя или значение current_value если option не найдена
        """
        current = self.current_value.value
        if not current:
            return "Не выбрано"

        # Ищем в списке options
        for option in self.available_options.value:
            if option.value == current:
                return option.label

        # Если не нашли, возвращаем значение
        return current

    async def _select_option(self, session_id: str, value: str) -> None:
        """Выбрать новую опцию.

        Args:
            session_id: ID сессии
            value: Значение опции
        """
        if not session_id:
            self.logger.warning(
                "Cannot select option: session_id is empty",
                config_id=self._config_id,
            )
            return

        self.is_loading.value = True
        self.error_message.value = None

        try:
            # Проверяем что опция доступна
            available_values = {opt.value for opt in self.available_options.value}
            if value not in available_values:
                raise ValueError(
                    f"Option {value} is not available for {self._config_id}"
                )

            # Отправляем запрос на смену через coordinator
            result = await self.coordinator.set_config_option(
                session_id=session_id,
                config_id=self._config_id,
                value=value,
            )

            # Обновляем текущее значение
            self.current_value.value = value

            # Обновляем список options из результата
            if result and "configOptions" in result:
                self.update_from_config(result["configOptions"], session_id)

            self.logger.info(
                "option_selected_successfully",
                config_id=self._config_id,
                session_id=session_id,
                value=value,
            )
        except Exception as e:
            error_msg = f"Failed to select option: {str(e)}"
            self.error_message.value = error_msg
            self.logger.exception(
                "Error selecting option",
                config_id=self._config_id,
                error=str(e),
            )
            raise
        finally:
            self.is_loading.value = False

    async def _open_modal(self) -> None:
        """Открыть модальное окно выбора."""
        self.is_modal_open.value = True
        self.logger.debug(
            "selector_modal_opened",
            config_id=self._config_id,
        )

    async def _close_modal(self) -> None:
        """Закрыть модальное окно выбора."""
        self.is_modal_open.value = False
        self.logger.debug(
            "selector_modal_closed",
            config_id=self._config_id,
        )

    @staticmethod
    def _parse_options(raw_options: list[dict[str, Any]]) -> list[ConfigOption]:
        """Распарсить raw options в ConfigOption.

        Args:
            raw_options: Список raw options от сервера

        Returns:
            Список ConfigOption
        """
        options = []
        for option in raw_options:
            if not isinstance(option, dict):
                continue

            value = option.get("value", "")
            if not value:
                continue

            label = option.get("name", value)
            description = option.get("description", "")

            # Собираем extra данные (pricing, provider_id и т.д.)
            extra = {}
            if "pricing" in option:
                extra["pricing"] = option["pricing"]
            if "_pricing" in option:
                extra["pricing"] = option["_pricing"]

            options.append(
                ConfigOption(
                    value=value,
                    label=label,
                    description=description,
                    extra=extra,
                )
            )

        return options


# ============================================================================
# Специализированные ViewModel для конкретных config options
# ============================================================================


class ModeSelectorViewModel(ConfigOptionSelectorViewModel):
    """ViewModel для выбора режима сессии (mode)."""

    def __init__(
        self,
        coordinator: Any,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        super().__init__(
            config_id="mode",
            title="Режим",
            coordinator=coordinator,
            event_bus=event_bus,
            logger=logger,
        )


class AgentSelectorViewModel(ConfigOptionSelectorViewModel):
    """ViewModel для выбора агента (_agent)."""

    def __init__(
        self,
        coordinator: Any,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        super().__init__(
            config_id="_agent",
            title="Агент",
            coordinator=coordinator,
            event_bus=event_bus,
            logger=logger,
        )


class StrategySelectorViewModel(ConfigOptionSelectorViewModel):
    """ViewModel для выбора стратегии выполнения (_active_strategy)."""

    def __init__(
        self,
        coordinator: Any,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        super().__init__(
            config_id="_active_strategy",
            title="Стратегия",
            coordinator=coordinator,
            event_bus=event_bus,
            logger=logger,
        )
