"""Константы и утилиты для ACP Protocol mode.

Mode определяет уровень разрешений и степень автономности агента:
- plan: Read-only, write/execute инструменты заблокированы
- standard: Permission request для каждого write/execute tool
- bypass: Auto-execute без подтверждения
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Допустимые значения mode
MODE_PLAN = "plan"
MODE_STANDARD = "standard"
MODE_BYPASS = "bypass"

VALID_MODES = {MODE_PLAN, MODE_STANDARD, MODE_BYPASS}

# Default mode
DEFAULT_MODE = MODE_STANDARD

# Backward compatibility mapping: old → new
OLD_TO_NEW_MODE: dict[str, str] = {
    "ask": MODE_STANDARD,
    "code": MODE_BYPASS,
    "architect": MODE_PLAN,
    "debug": MODE_STANDARD,
}

# Mode descriptions for ACP configOptions
MODE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    MODE_PLAN: {
        "name": "Plan",
        "description": (
            "Read-only planning mode. Agents can reason and plan, "
            "but cannot modify files or execute commands."
        ),
    },
    MODE_STANDARD: {
        "name": "Standard",
        "description": (
            "Confirm changes before execution. "
            "Agents request permission for each write/execute action."
        ),
    },
    MODE_BYPASS: {
        "name": "Bypass",
        "description": (
            "Full autonomy, no confirmation. "
            "Agents can write files and execute commands without user approval."
        ),
    },
}

# Tool kinds that are blocked in plan mode
PLAN_MODE_BLOCKED_KINDS = {"edit", "delete", "execute", "bash", "terminal"}
PLAN_MODE_ALLOWED_KINDS = {"read", "search", "think", "fetch", "move"}


def normalize_mode(mode: str) -> str:
    """Нормализовать значение mode с backward compatibility.

    Args:
        mode: Значение mode из config_values

    Returns:
        Нормализованное значение mode (plan, standard, bypass)
    """
    if mode in VALID_MODES:
        return mode

    # Backward compatibility
    if mode in OLD_TO_NEW_MODE:
        new_mode = OLD_TO_NEW_MODE[mode]
        logger.warning(
            "Deprecated mode '%s' automatically migrated to '%s'. "
            "Update your configuration to use the new value.",
            mode,
            new_mode,
        )
        return new_mode

    # Unknown → default
    logger.warning(
        "Unknown mode '%s', falling back to default '%s'",
        mode,
        DEFAULT_MODE,
    )
    return DEFAULT_MODE


def is_valid_mode(mode: str) -> bool:
    """Проверить валидность значения mode."""
    return mode in VALID_MODES


def is_mode_read_only(mode: str) -> bool:
    """Проверить, является ли mode read-only (plan)."""
    return mode == MODE_PLAN


def is_mode_auto_execute(mode: str) -> bool:
    """Проверить, разрешает ли mode auto-execute (bypass)."""
    return mode == MODE_BYPASS


def is_tool_blocked_in_plan_mode(tool_kind: str) -> bool:
    """Проверить, заблокирован ли инструмент в plan mode."""
    return tool_kind.lower() in PLAN_MODE_BLOCKED_KINDS
