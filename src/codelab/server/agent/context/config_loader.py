"""Загрузчик конфигурации Context Manager.

Загрузка: TOML [agents.context.*] -> ContextConfig,
затем env-overrides CODELAB_CONTEXT_* (приоритет выше TOML).

Депрекейт: agents.context.enable_fcm -> алиас на agents.context.enabled с warning.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from codelab.server.agent.context.models import ContextConfig

logger = logging.getLogger(__name__)

_ENV_PREFIX = "CODELAB_CONTEXT_"
_DEPRECATED_ENABLE_FCM = "agents.context.enable_fcm"

_BOOL_FIELDS = {
    "enabled",
    "gather_enabled",
    "recursive_dependencies",
    "use_tree_sitter",
    "use_tiktoken",
    "file_cache",
    "skeletonize",
    "incremental",
    "federation",
}
_INT_FIELDS = {
    "cache_max_files",
    "max_context_tokens",
    "reserved_tokens",
}
_FLOAT_FIELDS = {
    "system_share",
    "history_share",
    "tool_output_share",
    "response_buffer_share",
}


def load_context_config(
    toml_data: dict[str, Any] | None = None,
) -> ContextConfig:
    """Загрузить ContextConfig из TOML-данных с env-overrides.

    Args:
        toml_data: Словарь из TOML (секция [agents.context] или корень).
                   Если None, используется пустой словарь.

    Returns:
        ContextConfig с применёнными TOML и env-overrides.
    """
    if toml_data is None:
        toml_data = {}

    context_section = toml_data.get("agents", {}).get("context", {})
    if not context_section:
        context_section = toml_data.get("context", {})

    values: dict[str, Any] = {}

    for field_name in _BOOL_FIELDS | _INT_FIELDS | _FLOAT_FIELDS:
        if field_name in context_section:
            values[field_name] = context_section[field_name]

    _handle_deprecated_enable_fcm(context_section, values)

    config = ContextConfig(**values)

    config = _apply_env_overrides(config)

    return config


def _handle_deprecated_enable_fcm(
    context_section: dict[str, Any],
    values: dict[str, Any],
) -> None:
    """Обработать депрекейт enable_fcm -> enabled."""
    if "enable_fcm" in context_section:
        logger.warning(
            "agents.context.enable_fcm is deprecated, "
            "use agents.context.enabled instead. "
            "enable_fcm will be removed in a future version.",
        )
        if "enabled" not in values:
            values["enabled"] = context_section["enable_fcm"]


def _apply_env_overrides(config: ContextConfig) -> ContextConfig:
    """Применить env-overrides CODELAB_CONTEXT_* к конфигу.

    Env variables имеют приоритет над TOML.
    """
    overrides: dict[str, Any] = {}

    for field_name in _BOOL_FIELDS | _INT_FIELDS | _FLOAT_FIELDS:
        env_key = _ENV_PREFIX + field_name.upper()
        env_value = os.environ.get(env_key)
        if env_value is None:
            continue

        if field_name in _BOOL_FIELDS:
            overrides[field_name] = env_value.lower() in ("true", "1", "yes")
        elif field_name in _INT_FIELDS:
            try:
                overrides[field_name] = int(env_value)
            except ValueError:
                logger.warning(
                    "Invalid integer value for %s: %s",
                    env_key,
                    env_value,
                )
        elif field_name in _FLOAT_FIELDS:
            try:
                overrides[field_name] = float(env_value)
            except ValueError:
                logger.warning(
                    "Invalid float value for %s: %s",
                    env_key,
                    env_value,
                )

    if not overrides:
        return config

    current = {
        f: getattr(config, f)
        for f in _BOOL_FIELDS | _INT_FIELDS | _FLOAT_FIELDS
    }
    current.update(overrides)
    return ContextConfig(**current)
