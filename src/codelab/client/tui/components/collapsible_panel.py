"""CollapsiblePanel - сворачиваемая панель для группировки контента.

Модуль предоставляет компоненты для создания сворачиваемых секций UI:
- CollapsiblePanel: панель со сворачиваемым содержимым
- AccordionGroup: группа панелей (только одна открыта по умолчанию)

Это alias-модуль, основная реализация находится в panel.py.
"""

from __future__ import annotations

# Реэкспорт из panel.py
from .panel import AccordionPanel, CollapsiblePanel

# Alias для совместимости с требованиями задачи
# AccordionGroup - альтернативное имя для AccordionPanel
AccordionGroup = AccordionPanel

__all__ = [
    "CollapsiblePanel",
    "AccordionGroup",
    "AccordionPanel",  # Для обратной совместимости
]
