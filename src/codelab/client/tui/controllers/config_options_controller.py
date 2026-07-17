"""Контроллер фан-аута обновлений config options по selector-ViewModel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codelab.client.presentation.config_option_selector_view_model import (
        AgentSelectorViewModel,
        ModeSelectorViewModel,
        StrategySelectorViewModel,
    )
    from codelab.client.presentation.model_selector_view_model import ModelSelectorViewModel


class ConfigOptionsController:
    """Раздаёт обновления configOptions в model/mode/agent/strategy селекторы."""

    def __init__(
        self,
        model_selector_vm: ModelSelectorViewModel,
        mode_selector_vm: ModeSelectorViewModel,
        agent_selector_vm: AgentSelectorViewModel,
        strategy_selector_vm: StrategySelectorViewModel,
        logger: Any,
    ) -> None:
        self._model_selector_vm = model_selector_vm
        self._mode_selector_vm = mode_selector_vm
        self._agent_selector_vm = agent_selector_vm
        self._strategy_selector_vm = strategy_selector_vm
        self._logger = logger

    def apply(self, event: Any) -> None:
        """Обновляет все selector-ViewModel из ConfigOptionUpdatedEvent."""
        session_id = getattr(event, "session_id", None)
        config_options = getattr(event, "config_options", [])

        if not (session_id and config_options):
            return

        self._logger.debug(
            "config_option_updated",
            session_id=session_id,
            config_options_count=len(config_options),
        )
        self._model_selector_vm.update_models_from_config(
            config_options=config_options,
            session_id=session_id,
        )
        for selector_vm in (
            self._mode_selector_vm,
            self._agent_selector_vm,
            self._strategy_selector_vm,
        ):
            selector_vm.update_from_config(
                config_options=config_options,
                session_id=session_id,
            )
