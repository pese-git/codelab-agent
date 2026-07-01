"""Загрузчик конфигурации агентов из 4 источников.

Источники (от низшего к высшему приоритету):
1. ~/.codelab/codelab.toml → [agents.definitions.*]
2. ~/.codelab/agents/*.md
3. codelab.toml → [agents.definitions.*]
4. .codelab/agents/*.md

Override логика: каждый источник перезаписывает предыдущий.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from codelab.server.agent.config.models import (
    AgentMarkdownConfig,
    AgentRole,
    AgentTOMLConfig,
)
from codelab.shared.logging import resolve_codelab_home

logger = logging.getLogger(__name__)

# Regex для YAML frontmatter
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


class AgentConfigLoader:
    """Загрузчик конфигурации агентов из TOML и Markdown."""

    def __init__(
        self,
        global_config_dir: Path | None = None,
        project_config_dir: Path | None = None,
    ) -> None:
        self.global_config_dir = global_config_dir or resolve_codelab_home()
        self.project_config_dir = project_config_dir or Path(".codelab")

    def load_all(
        self,
        global_toml: dict[str, Any] | None = None,
        project_toml: dict[str, Any] | None = None,
    ) -> dict[str, AgentMarkdownConfig]:
        """Загрузить все конфигурации агентов из 4 источников.

        Порядок (override): global TOML → global MD → project TOML → project MD

        Args:
            global_toml: Конфигурация из ~/.codelab/codelab.toml
            project_toml: Конфигурация из codelab.toml

        Returns:
            dict[agent_name] → AgentMarkdownConfig
        """
        result: dict[str, AgentMarkdownConfig] = {}

        # 1. Global TOML (низший приоритет)
        if global_toml:
            result.update(self._load_toml_definitions(global_toml))

        # 2. Global Markdown
        result.update(self._load_markdown_dir(self.global_config_dir / "agents"))

        # 3. Project TOML
        if project_toml:
            result.update(self._load_toml_definitions(project_toml))

        # 4. Project Markdown (высший приоритет)
        result.update(self._load_markdown_dir(self.project_config_dir / "agents"))

        logger.info("Loaded %d agent configurations", len(result))
        return result

    def _load_toml_definitions(
        self, toml_data: dict[str, Any]
    ) -> dict[str, AgentMarkdownConfig]:
        """Извлечь определения агентов из TOML."""
        result: dict[str, AgentMarkdownConfig] = {}
        agents_section = toml_data.get("agents", {})
        definitions = agents_section.get("definitions", {})

        for name, cfg_dict in definitions.items():
            try:
                # Backward compatibility: mode → role
                if "role" not in cfg_dict and "mode" in cfg_dict:
                    cfg_dict = dict(cfg_dict)
                    cfg_dict["role"] = cfg_dict.pop("mode")
                    logger.warning(
                        "Agent '%s': поле 'mode' deprecated в TOML, используйте 'role'",
                        name,
                    )
                toml_cfg = AgentTOMLConfig(**cfg_dict)
                md_cfg = self._toml_to_markdown(name, toml_cfg)
                result[name] = md_cfg
            except Exception:
                logger.exception("Failed to parse TOML config for agent '%s'", name)

        return result

    def _load_markdown_dir(
        self, directory: Path
    ) -> dict[str, AgentMarkdownConfig]:
        """Загрузить все .md файлы из директории."""
        result: dict[str, AgentMarkdownConfig] = {}

        if not directory.exists() or not directory.is_dir():
            return result

        for md_file in sorted(directory.glob("*.md")):
            try:
                cfg = self._parse_markdown(md_file)
                result[cfg.name] = cfg
            except Exception:
                logger.exception("Failed to parse Markdown config: %s", md_file)

        return result

    def _parse_markdown(self, path: Path) -> AgentMarkdownConfig:
        """Парсить Markdown файл с YAML frontmatter.

        Формат:
        ---
        name: coder
        role: primary
        model: openai/gpt-4o
        ---
        System prompt body...
        """
        content = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(content)

        if not match:
            # Нет frontmatter — используем имя файла как name
            return AgentMarkdownConfig(
                name=path.stem,
                prompt=content.strip(),
            )

        frontmatter_str, body = match.groups()

        # Парсим YAML frontmatter вручную (без pyyaml)
        frontmatter = self._parse_yaml_simple(frontmatter_str)

        # Извлекаем role как enum (с backward compatibility для mode)
        if "role" in frontmatter:
            role_str = frontmatter.pop("role")
        elif "mode" in frontmatter:
            role_str = frontmatter.pop("mode")
            logger.warning(
                "Agent '%s': поле 'mode' deprecated, используйте 'role'", path.stem
            )
        else:
            role_str = "primary"
        try:
            role = AgentRole(role_str)
        except ValueError:
            role = AgentRole.PRIMARY

        # Имя из frontmatter или из файла
        name = frontmatter.pop("name", path.stem)

        # permissions — особый формат (может быть dict или inline)
        permissions_raw = frontmatter.pop("permissions", {})
        permissions: dict[str, bool] = {}
        if isinstance(permissions_raw, dict):
            permissions = {k: bool(v) for k, v in permissions_raw.items()}

        return AgentMarkdownConfig(
            name=name,
            role=role,
            prompt=body.strip(),
            permissions=permissions,
            **frontmatter,  # extra="allow"
        )

    def _parse_yaml_simple(self, text: str) -> dict[str, Any]:
        """Простой парсер YAML frontmatter без внешних зависимостей.

        Поддерживает:
        - scalar values: key: value
        - nested dicts: key:\n  subkey: value
        - inline lists: key: [a, b, c]
        - booleans: true/false
        - numbers: int/float
        - strings: quoted or unquoted
        """
        result: dict[str, Any] = {}
        current_key: str | None = None
        current_dict: dict[str, Any] | None = None

        for line in text.strip().split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Nested dict (indented line)
            if line.startswith("  ") and current_key and current_dict is not None:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()
                current_dict[key] = self._parse_value(value)
                continue

            # Top-level key
            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                # Check if it's a nested dict (value is empty)
                if not value:
                    current_key = key
                    current_dict = {}
                    result[key] = current_dict
                else:
                    current_key = None
                    current_dict = None
                    result[key] = self._parse_value(value)

        return result

    def _parse_value(self, value: str) -> Any:
        """Парсить YAML value."""
        if not value:
            return ""

        # Inline list: [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            return [item.strip().strip("\"'") for item in items if item.strip()]

        # Quoted string
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]

        # Boolean
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        # None
        if value.lower() in ("null", "~"):
            return None

        # Number
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass

        # String
        return value

    def _toml_to_markdown(
        self, name: str, toml_cfg: AgentTOMLConfig
    ) -> AgentMarkdownConfig:
        """Конвертировать TOML конфигурацию в Markdown конфигурацию."""
        return AgentMarkdownConfig(
            name=name,
            enabled=toml_cfg.enabled,
            role=toml_cfg.role,
            priority=toml_cfg.priority,
            model=toml_cfg.model,
            temperature=toml_cfg.temperature,
            max_steps=toml_cfg.max_steps,
            tools=list(toml_cfg.tools),
            permissions=dict(toml_cfg.permissions),
            prompt=toml_cfg.prompt or "",
            **(toml_cfg.model_extra or {}),  # extra поля
        )
