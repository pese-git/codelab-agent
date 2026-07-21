"""KeyboardManager - централизованное управление горячими клавишами.

Обеспечивает:
- Регистрацию и управление горячими клавишами
- Группировку клавиш по категориям
- Получение списка всех доступных hotkeys для справки
- Конфликт-чекинг для предотвращения дублирования
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from textual.app import App

logger = structlog.get_logger(__name__)


class HotkeyCategory(Enum):
    """Категории горячих клавиш для группировки в справке."""

    NAVIGATION = "navigation"  # Навигация
    SESSION = "session"  # Управление сессиями
    EDITING = "editing"  # Редактирование
    VIEW = "view"  # Отображение
    SYSTEM = "system"  # Системные


@dataclass
class HotkeyBinding:
    """Описание горячей клавиши.

    Атрибуты:
        key: Комбинация клавиш (например, "ctrl+b")
        action: Имя действия в Textual
        description: Описание действия для пользователя
        category: Категория для группировки в справке
        show_in_help: Показывать ли в справке
        priority: Приоритет (для сортировки)
    """

    key: str
    action: str
    description: str
    category: HotkeyCategory = HotkeyCategory.NAVIGATION
    show_in_help: bool = True
    priority: int = 100


@dataclass
class HotkeyGroup:
    """Группа горячих клавиш для отображения в справке."""

    category: HotkeyCategory
    name: str
    bindings: list[HotkeyBinding] = field(default_factory=list)


# Стандартные горячие клавиши CodeLab TUI.
#
# ЕДИНЫЙ ИСТОЧНИК ИСТИНЫ о раскладке: `ACPClientApp.BINDINGS` собирается из этого
# списка через get_default_textual_bindings(), а справка (`HelpModal`) — через
# get_help_groups(). Порядок объявления совпадает с порядком в footer App.
# Раскладка канонизирована по фактически работавшему `App.BINDINGS` (tech-debt #16):
# менять клавишу здесь = менять контракт UX.
DEFAULT_BINDINGS: list[HotkeyBinding] = [
    HotkeyBinding("ctrl+q", "quit", "Выход", HotkeyCategory.SYSTEM, priority=10),
    HotkeyBinding("ctrl+n", "new_session", "Новая сессия", HotkeyCategory.SESSION, priority=20),
    HotkeyBinding("ctrl+b", "toggle_sidebar", "Sidebar", HotkeyCategory.NAVIGATION, priority=40),
    HotkeyBinding(
        "ctrl+s", "focus_session_list", "Список сессий", HotkeyCategory.NAVIGATION, priority=50
    ),
    HotkeyBinding(
        "ctrl+j", "next_session", "Следующая сессия", HotkeyCategory.SESSION, priority=60
    ),
    HotkeyBinding(
        "ctrl+k", "previous_session", "Предыдущая сессия", HotkeyCategory.SESSION, priority=70
    ),
    HotkeyBinding("ctrl+l", "clear_chat", "Очистить чат", HotkeyCategory.SESSION, priority=80),
    HotkeyBinding("ctrl+h", "open_help", "Справка", HotkeyCategory.SYSTEM, priority=90),
    HotkeyBinding("?", "show_hotkeys", "Горячие клавиши", HotkeyCategory.SYSTEM, priority=100),
    HotkeyBinding(
        "ctrl+tab", "next_sidebar_tab", "Вкладка sidebar", HotkeyCategory.NAVIGATION, priority=110
    ),
    HotkeyBinding(
        "ctrl+shift+tab",
        "previous_sidebar_tab",
        "Предыдущая вкладка",
        HotkeyCategory.NAVIGATION,
        priority=120,
    ),
    HotkeyBinding(
        "tab", "cycle_focus", "Переключить фокус", HotkeyCategory.NAVIGATION, priority=140
    ),
    HotkeyBinding("ctrl+c", "cancel_prompt", "Отменить", HotkeyCategory.SESSION, priority=150),
    HotkeyBinding("ctrl+m", "select_model", "Выбрать модель", HotkeyCategory.VIEW, priority=160),
    HotkeyBinding(
        "ctrl+shift+m", "select_mode", "Выбрать режим", HotkeyCategory.VIEW, priority=170
    ),
    HotkeyBinding("ctrl+a", "select_agent", "Выбрать агента", HotkeyCategory.VIEW, priority=180),
    HotkeyBinding(
        "ctrl+shift+a", "select_strategy", "Выбрать стратегию", HotkeyCategory.VIEW, priority=190
    ),
    HotkeyBinding(
        "ctrl+p", "command_palette", "Палитра команд", HotkeyCategory.SYSTEM, priority=200
    ),
    HotkeyBinding("ctrl+t", "toggle_theme", "Переключить тему", HotkeyCategory.VIEW, priority=210),
    HotkeyBinding("escape", "close_modal", "Закрыть", HotkeyCategory.SYSTEM, priority=220),
]


def get_default_textual_bindings() -> list[tuple[str, str, str]]:
    """Единый источник `App.BINDINGS`: (key, action, description) в порядке объявления.

    App собирает свои BINDINGS отсюда, чтобы раскладка не расходилась с
    KeyboardManager/справкой (tech-debt #16).
    """
    return [(b.key, b.action, b.description) for b in DEFAULT_BINDINGS]


# Названия категорий на русском
CATEGORY_NAMES: dict[HotkeyCategory, str] = {
    HotkeyCategory.SYSTEM: "Системные",
    HotkeyCategory.SESSION: "Сессии",
    HotkeyCategory.NAVIGATION: "Навигация",
    HotkeyCategory.VIEW: "Отображение",
    HotkeyCategory.EDITING: "Редактирование",
}


class KeyboardManager:
    """Централизованный менеджер горячих клавиш.

    Управляет регистрацией и организацией горячих клавиш приложения.
    Предоставляет API для получения списка hotkeys по категориям.
    """

    def __init__(self, app: App | None = None) -> None:
        """Инициализирует KeyboardManager.

        Args:
            app: Textual App для привязки действий (опционально)
        """
        self._app = app
        self._bindings: dict[str, HotkeyBinding] = {}
        self._custom_handlers: dict[str, Callable[[], None]] = {}
        self._logger = logger.bind(component="keyboard_manager")

        # Регистрируем стандартные binding'и
        for binding in DEFAULT_BINDINGS:
            self.register(binding)

    def register(self, binding: HotkeyBinding) -> None:
        """Регистрирует горячую клавишу.

        Args:
            binding: Описание горячей клавиши

        Raises:
            ValueError: Если клавиша уже зарегистрирована
        """
        key = binding.key.lower()
        if key in self._bindings:
            existing = self._bindings[key]
            self._logger.warning(
                "hotkey_already_registered",
                key=key,
                existing_action=existing.action,
                new_action=binding.action,
            )
        self._bindings[key] = binding
        self._logger.debug("hotkey_registered", key=key, action=binding.action)

    def unregister(self, key: str) -> bool:
        """Удаляет регистрацию горячей клавиши.

        Args:
            key: Комбинация клавиш для удаления

        Returns:
            True если клавиша была удалена, False если не найдена
        """
        key = key.lower()
        if key in self._bindings:
            del self._bindings[key]
            self._logger.debug("hotkey_unregistered", key=key)
            return True
        return False

    def get_binding(self, key: str) -> HotkeyBinding | None:
        """Получает описание горячей клавиши.

        Args:
            key: Комбинация клавиш

        Returns:
            HotkeyBinding или None если не найдена
        """
        return self._bindings.get(key.lower())

    def get_all_bindings(self) -> list[HotkeyBinding]:
        """Возвращает все зарегистрированные горячие клавиши.

        Returns:
            Список всех binding'ов, отсортированный по приоритету
        """
        return sorted(self._bindings.values(), key=lambda b: b.priority)

    def get_bindings_by_category(self) -> dict[HotkeyCategory, list[HotkeyBinding]]:
        """Возвращает горячие клавиши, сгруппированные по категориям.

        Returns:
            Словарь {категория: список binding'ов}
        """
        result: dict[HotkeyCategory, list[HotkeyBinding]] = {}
        for binding in self._bindings.values():
            if not binding.show_in_help:
                continue
            if binding.category not in result:
                result[binding.category] = []
            result[binding.category].append(binding)

        # Сортируем binding'и внутри каждой категории
        for category in result:
            result[category].sort(key=lambda b: b.priority)

        return result

    def get_help_groups(self) -> list[HotkeyGroup]:
        """Возвращает группы горячих клавиш для отображения в справке.

        Returns:
            Список групп, отсортированный по категориям
        """
        by_category = self.get_bindings_by_category()
        groups: list[HotkeyGroup] = []

        # Порядок категорий в справке
        category_order = [
            HotkeyCategory.SYSTEM,
            HotkeyCategory.SESSION,
            HotkeyCategory.NAVIGATION,
            HotkeyCategory.VIEW,
            HotkeyCategory.EDITING,
        ]

        for category in category_order:
            if category in by_category:
                groups.append(
                    HotkeyGroup(
                        category=category,
                        name=CATEGORY_NAMES.get(category, category.value),
                        bindings=by_category[category],
                    )
                )

        return groups

    def format_key(self, key: str) -> str:
        """Форматирует клавишу для отображения.

        Args:
            key: Комбинация клавиш (например, "ctrl+b")

        Returns:
            Отформатированная строка (например, "Ctrl+B")
        """
        parts = key.split("+")
        formatted_parts = []

        for part in parts:
            part_lower = part.lower()
            if part_lower == "ctrl":
                formatted_parts.append("Ctrl")
            elif part_lower == "shift":
                formatted_parts.append("Shift")
            elif part_lower == "alt":
                formatted_parts.append("Alt")
            elif part_lower == "escape":
                formatted_parts.append("Esc")
            elif part_lower == "tab":
                formatted_parts.append("Tab")
            else:
                formatted_parts.append(part.upper())

        return "+".join(formatted_parts)

    def get_textual_bindings(self) -> list[tuple[str, str, str]]:
        """Возвращает binding'и в формате Textual.

        Returns:
            Список кортежей (key, action, description)
        """
        return [(b.key, b.action, b.description) for b in self.get_all_bindings()]

    def register_handler(self, action: str, handler: Callable[[], None]) -> None:
        """Регистрирует кастомный обработчик для действия.

        Args:
            action: Имя действия
            handler: Функция-обработчик
        """
        self._custom_handlers[action] = handler
        self._logger.debug("custom_handler_registered", action=action)

    def execute(self, action: str) -> bool:
        """Выполняет действие по имени.

        Args:
            action: Имя действия

        Returns:
            True если действие выполнено, False если не найдено
        """
        if action in self._custom_handlers:
            try:
                self._custom_handlers[action]()
                return True
            except Exception as e:
                self._logger.error("handler_execution_error", action=action, error=str(e))
                return False

        # Если есть app, пытаемся выполнить action через него
        if self._app is not None:
            try:
                self._app.action(action)
                return True
            except Exception:
                pass

        return False


# Глобальный экземпляр для использования в приложении
_keyboard_manager: KeyboardManager | None = None


def get_keyboard_manager() -> KeyboardManager:
    """Возвращает глобальный экземпляр KeyboardManager.

    Returns:
        KeyboardManager
    """
    global _keyboard_manager
    if _keyboard_manager is None:
        _keyboard_manager = KeyboardManager()
    return _keyboard_manager


def set_keyboard_manager(manager: KeyboardManager) -> None:
    """Устанавливает глобальный экземпляр KeyboardManager.

    Args:
        manager: KeyboardManager для установки
    """
    global _keyboard_manager
    _keyboard_manager = manager
