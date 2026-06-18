"""ViewModel для управления планом агента.

Отвечает за:
- Управление текстом плана
- Отслеживание наличия активного плана
- Реактивное обновление UI при изменениях плана
"""

from typing import Any

from codelab.client.presentation.base_view_model import BaseViewModel
from codelab.client.presentation.observable import Observable


class PlanViewModel(BaseViewModel):
    """ViewModel для отображения плана агента.
    
    Хранит состояние плана:
    - plan_text: текст плана
    - has_plan: флаг наличия активного плана
    
    Пример использования:
        >>> vm = PlanViewModel()
        >>> 
        >>> # Подписаться на изменения плана
        >>> vm.plan_text.subscribe(lambda p: print(f"Plan: {p}"))
        >>> 
        >>> # Установить новый план
        >>> vm.set_plan("1. Задача A\\n2. Задача B")
        >>> 
        >>> # Очистить план
        >>> vm.clear_plan()
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        """Инициализировать PlanViewModel.
        
        Args:
            event_bus: EventBus для публикации/подписки на события
            logger: Logger для логирования
        """
        super().__init__(event_bus, logger)
        
        # Observable свойства
        self._plan_text: Observable[str] = Observable("")
        self._has_plan: Observable[bool] = Observable(False)

    @property
    def plan_text(self) -> Observable:
        """Текст плана агента."""
        return self._plan_text

    @property
    def has_plan(self) -> Observable:
        """Есть ли активный план."""
        return self._has_plan

    def set_plan(self, plan: str) -> None:
        """Установить новый план.
        
        Args:
            plan: Текст плана
        """
        self._plan_text.value = plan
        self._has_plan.value = bool(plan.strip())

    def clear_plan(self) -> None:
        """Очистить план."""
        self._plan_text.value = ""
        self._has_plan.value = False
