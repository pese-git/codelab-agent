"""Events infrastructure - модуль для управления доменными событиями.

Содержит реализацию Event Bus и обработчиков событий для слабой связанности
компонентов системы.
"""

from codelab.client.infrastructure.events.bus import EventBus

__all__ = ["EventBus"]
