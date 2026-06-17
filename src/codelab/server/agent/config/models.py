"""Конфигурация мультиагентной системы.

Pydantic модели для:
- AgentRole — роль агента (primary, subagent, orchestrator)
- AgentPermission — разрешения агента
- AgentTOMLConfig — конфигурация из TOML
- AgentsGlobalConfig — глобальные настройки [agents]
- AgentMarkdownConfig — конфигурация из Markdown
- ResolvedAgent — разрешённая конфигурация агента
- SessionMetrics — метрики сессии
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentRole(StrEnum):
    """Роль агента в мультиагентной системе."""

    PRIMARY = "primary"
    SUBAGENT = "subagent"
    ORCHESTRATOR = "orchestrator"


class AgentPermission(BaseModel):
    """Разрешения агента."""

    model_config = ConfigDict(frozen=True)

    edit: bool = False
    bash: bool = False
    webfetch: bool = False
    task: bool = False


class AgentTOMLConfig(BaseModel):
    """Конфигурация агента из TOML.

    extra="allow" позволяет vendor-specific параметры.
    """

    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    role: AgentRole = AgentRole.PRIMARY
    priority: int = 99
    model: str | None = None
    temperature: float | None = None
    max_steps: int | None = None
    tools: list[str] = Field(default_factory=list)
    permissions: dict[str, bool] = Field(default_factory=dict)
    prompt: str | None = None


class AgentsGlobalConfig(BaseModel):
    """Глобальные настройки мультиагентности из секции [agents]."""

    model_config = ConfigDict(extra="allow")

    role: AgentRole = AgentRole.PRIMARY
    fallback_role: AgentRole = AgentRole.PRIMARY
    default_model: str = "openai/gpt-4o"
    max_steps: int = 10
    # TokenSlicer конфигурация
    slicer_model: str = "openai/gpt-4o-mini"
    max_sliced_tokens: int = 120
    slicer_skip_threshold: int = 300
    # Context compaction
    context_window_limit: int = 128000
    compaction_reserved_tokens: int = 4096
    # Debug mode
    debug: bool = False
    # Определения агентов из TOML
    definitions: dict[str, AgentTOMLConfig] = Field(default_factory=dict)


class AgentMarkdownConfig(BaseModel):
    """Конфигурация агента из Markdown файла.

    extra="allow" позволяет vendor-specific параметры из frontmatter.
    """

    model_config = ConfigDict(extra="allow")

    name: str = ""
    enabled: bool = True
    role: AgentRole = AgentRole.PRIMARY
    priority: int = 99
    model: str | None = None
    temperature: float | None = None
    max_steps: int | None = None
    tools: list[str] = Field(default_factory=list)
    permissions: dict[str, bool] = Field(default_factory=dict)
    prompt: str = ""


class ResolvedAgent(BaseModel):
    """Разрешённая конфигурация агента с применёнными defaults."""

    name: str
    enabled: bool = True
    role: AgentRole = AgentRole.PRIMARY
    priority: int = 99
    model: str = ""
    temperature: float = 0.0
    max_steps: int | None = None
    tools: list[str] = Field(default_factory=list)
    permissions: AgentPermission = Field(default_factory=AgentPermission)
    prompt: str = ""
    additional_params: dict[str, Any] = Field(default_factory=dict)


class SessionMetrics(BaseModel):
    """Метрики сессии."""

    total_time_sec: float = 0.0
    total_llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    task_success: bool | None = None
    agent_breakdown: dict[str, dict[str, Any]] = Field(default_factory=dict)
