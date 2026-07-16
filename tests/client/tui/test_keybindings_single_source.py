"""Guardrail: единый источник раскладки клавиш (tech-debt #16).

Ловит повторное расхождение `App.BINDINGS` ↔ `KeyboardManager.DEFAULT_BINDINGS`,
дубли клавиш/действий и биндинги без обработчика.
"""

from __future__ import annotations

from codelab.client.tui.app import ACPClientApp
from codelab.client.tui.components.keyboard_manager import (
    DEFAULT_BINDINGS,
    get_default_textual_bindings,
)

# tech-debt: эти действия объявлены в раскладке, но пока НЕ имеют `action_*`
# обработчиков в App (мёртвые биндинги, обнаружены при #16). Набор заморожен —
# см. также #16 в doc/internals/tech-debt.md.
_KNOWN_ACTIONS_WITHOUT_HANDLER = {
    "retry_prompt",
    "clear_chat",
    "open_terminal_output",
    "cycle_focus",
}
# Обрабатываются самим Textual (App.action_quit и т.п.), не объявляются в App.
_TEXTUAL_BUILTIN_ACTIONS = {"quit"}


def test_app_bindings_derived_from_single_source() -> None:
    """App.BINDINGS собирается ровно из KeyboardManager.DEFAULT_BINDINGS."""
    assert list(ACPClientApp.BINDINGS) == get_default_textual_bindings()


def test_no_duplicate_keys() -> None:
    """Одна клавиша не должна быть привязана к двум действиям."""
    keys = [b.key for b in DEFAULT_BINDINGS]
    assert len(keys) == len(set(keys)), f"дублирующиеся клавиши: {keys}"


def test_no_duplicate_actions() -> None:
    """Одно действие не должно висеть на двух разных клавишах."""
    actions = [b.action for b in DEFAULT_BINDINGS]
    assert len(actions) == len(set(actions)), f"дублирующиеся действия: {actions}"


def test_every_binding_has_handler_or_is_known_gap() -> None:
    """Каждый action либо имеет `action_*` в App, либо в известном списке пробелов.

    Заваливается, если добавили новый биндинг без обработчика (регресс) или
    реализовали один из известных пробелов (нужно обновить список).
    """
    missing = {
        b.action
        for b in DEFAULT_BINDINGS
        if b.action not in _TEXTUAL_BUILTIN_ACTIONS
        and not hasattr(ACPClientApp, f"action_{b.action}")
    }
    assert missing == _KNOWN_ACTIONS_WITHOUT_HANDLER
