"""ModelSelectorViewModel для управления выбором LLM модели.

Отвечает за:
- Хранение списка доступных моделей из configOptions
- Текущую выбранную модель
- Отправку запросов на смену модели через coordinator
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codelab.client.presentation.base_view_model import BaseViewModel
from codelab.client.presentation.observable import Observable, ObservableCommand


@dataclass
class ModelOption:
    """Опция модели для выбора.

    Атрибуты:
        value: Уникальный идентификатор (например, "openai/gpt-4o")
        label: Отображаемое имя (например, "gpt-4o")
        description: Описание модели (например, "128,000 context")
        pricing: Информация о стоимости (опционально)
    """

    value: str
    label: str
    description: str = ""
    pricing: str = ""

    @property
    def provider_id(self) -> str:
        """ID провайдера из полного идентификатора."""
        return self.value.split("/")[0] if "/" in self.value else ""

    @property
    def model_id(self) -> str:
        """ID модели из полного идентификатора."""
        return self.value.split("/")[1] if "/" in self.value else self.value


class ModelSelectorViewModel(BaseViewModel):
    """ViewModel для управления выбором LLM модели.

    Хранит состояние выбора модели:
    - available_models: список доступных моделей
    - current_model: текущая выбранная модель
    - is_loading: флаг загрузки
    - error_message: последняя ошибка

    Пример использования:
        >>> coordinator = SessionCoordinator(...)
        >>> vm = ModelSelectorViewModel(coordinator)
        >>>
        >>> # Обновить список моделей из configOptions
        >>> vm.update_models_from_config(config_options)
        >>>
        >>> # Выбрать модель
        >>> await vm.select_model_cmd.execute("session_1", "anthropic/claude-sonnet-4")
    """

    def __init__(
        self,
        coordinator: Any,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        """Инициализировать ModelSelectorViewModel.

        Args:
            coordinator: SessionCoordinator для работы с сервером
            event_bus: EventBus для публикации/подписки на события
            logger: Logger для логирования
        """
        super().__init__(event_bus, logger)
        self.coordinator = coordinator

        # Observable свойства
        self.available_models: Observable[list[ModelOption]] = Observable([])
        self.current_model: Observable[str | None] = Observable(None)
        self.is_loading: Observable[bool] = Observable(False)
        self.error_message: Observable[str | None] = Observable(None)
        self.is_modal_open: Observable[bool] = Observable(False)

        # Кэш configOptions по session_id
        self._config_cache: dict[str, dict[str, Any]] = {}

        # Observable команды
        self.select_model_cmd = ObservableCommand(self._select_model)
        self.open_modal_cmd = ObservableCommand(self._open_modal)
        self.close_modal_cmd = ObservableCommand(self._close_modal)

    def update_models_from_config(
        self,
        config_options: list[dict[str, Any]],
        session_id: str | None = None,
    ) -> None:
        """Обновить список моделей из configOptions.

        Ищет config option с category="model" и извлекает модели.

        Args:
            config_options: Список config options от сервера
            session_id: ID сессии для кэширования (опционально)
        """
        # Кэшируем все config options
        if session_id:
            self._config_cache[session_id] = {
                opt["id"]: opt for opt in config_options if "id" in opt
            }

        # Ищем model config option
        model_config = None
        for option in config_options:
            if option.get("category") == "model":
                model_config = option
                break

        if model_config is None:
            self.logger.debug("model_config_option_not_found")
            return

        # Извлекаем текущую модель
        current_value = model_config.get("currentValue") or model_config.get("default")
        if current_value:
            self.current_model.value = current_value

        # Извлекаем список моделей
        raw_options = model_config.get("options", [])
        models = self._parse_model_options(raw_options)

        self.available_models.value = models
        self.logger.info(
            "models_updated_from_config",
            model_count=len(models),
            current_model=current_value,
        )

    def update_current_model(self, model_value: str) -> None:
        """Обновить текущую модель напрямую.

        Args:
            model_value: Новое значение модели (например, "openai/gpt-4o")
        """
        self.current_model.value = model_value
        self.logger.debug("current_model_updated", model=model_value)

    def get_current_model_label(self) -> str:
        """Получить отображаемое имя текущей модели.

        Returns:
            Отображаемое имя или значение current_model если модель не найдена
        """
        current = self.current_model.value
        if not current:
            return "Не выбрано"

        # Ищем в списке моделей
        for model in self.available_models.value:
            if model.value == current:
                return model.label

        # Если не нашли, возвращаем часть после /
        return current.split("/")[-1] if "/" in current else current

    async def _select_model(self, session_id: str, model_value: str) -> None:
        """Выбрать новую модель.

        Args:
            session_id: ID сессии
            model_value: Значение модели (например, "anthropic/claude-sonnet-4")
        """
        if not session_id:
            self.logger.warning("Cannot select model: session_id is empty")
            return

        self.is_loading.value = True
        self.error_message.value = None

        try:
            # Проверяем что модель доступна
            available_values = {m.value for m in self.available_models.value}
            if model_value not in available_values:
                raise ValueError(f"Model {model_value} is not available")

            # Отправляем запрос на смену модели через coordinator
            result = await self.coordinator.set_config_option(
                session_id=session_id,
                config_id="model",
                value=model_value,
            )

            # Обновляем текущую модель
            self.current_model.value = model_value

            # Обновляем список моделей из результата
            if result and "configOptions" in result:
                self.update_models_from_config(result["configOptions"], session_id)

            self.logger.info(
                "model_selected_successfully",
                session_id=session_id,
                model=model_value,
            )
        except Exception as e:
            error_msg = f"Failed to select model: {str(e)}"
            self.error_message.value = error_msg
            self.logger.exception("Error selecting model", error=str(e))
            raise
        finally:
            self.is_loading.value = False

    async def _open_modal(self) -> None:
        """Открыть модальное окно выбора модели."""
        self.is_modal_open.value = True
        self.logger.debug("model_selector_modal_opened")

    async def _close_modal(self) -> None:
        """Закрыть модальное окно выбора модели."""
        self.is_modal_open.value = False
        self.logger.debug("model_selector_modal_closed")

    @staticmethod
    def _parse_model_options(raw_options: list[dict[str, Any]]) -> list[ModelOption]:
        """Распарсить raw options в ModelOption.

        Args:
            raw_options: Список raw options от сервера

        Returns:
            Список ModelOption
        """
        models = []
        for option in raw_options:
            if not isinstance(option, dict):
                continue

            value = option.get("value", "")
            if not value:
                continue

            label = option.get("name", value.split("/")[-1])
            description = option.get("description", "")
            pricing = option.get("_pricing", "")

            models.append(
                ModelOption(
                    value=value,
                    label=label,
                    description=description,
                    pricing=pricing,
                )
            )

        return models
