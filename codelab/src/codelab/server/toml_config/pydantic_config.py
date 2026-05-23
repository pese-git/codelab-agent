"""Pydantic Settings models for TOML configuration.

Заменяет кастомный toml_loader.py на Pydantic Settings с TomlConfigSettingsSource.
Поддерживает:
- Парсинг TOML файлов через SettingsConfigDict(toml_file=...)
- Валидацию типов через Pydantic
- Environment variable expansion через field_validator
- Генерацию ProviderInfo/ModelInfo для LLMProviderRegistry
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from codelab.server.llm.models import ModelInfo, ProviderInfo


def _humanize_name(model_id: str) -> str:
    """Преобразует model_id в читаемое имя.

    Заменяет дефисы и подчёркивания на пробелы, применяет title case.
    Примеры:
        gpt-4o → Gpt 4o
        llama3_1_70b → Llama3 1 70b
        claude-sonnet-4 → Claude Sonnet 4
    """
    return re.sub(r"[-_]", " ", model_id).title()


def _expand_env_vars(value: str) -> str:
    """Раскрывает переменные окружения в строке.

    Поддерживает формат ${VAR_NAME} и $VAR_NAME.
    """
    if not value or "$" not in value:
        return value

    result = value
    # ${VAR} format
    for match in re.finditer(r"\$\{([^}]+)\}", value):
        var_name = match.group(1)
        env_value = os.environ.get(var_name, "")
        result = result.replace(match.group(0), env_value)

    # $VAR format (без скобок)
    for match in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*)", result):
        var_name = match.group(1)
        env_value = os.environ.get(var_name, "")
        result = result.replace(match.group(0), env_value)

    return result


class ModelConfig(BaseModel):
    """Конфигурация конкретной модели.

    Атрибуты:
        context_window: Размер контекстного окна
        max_output_tokens: Максимальное количество выходных токенов
        cost_per_input_token: Стоимость входного токена (USD)
        cost_per_output_token: Стоимость выходного токена (USD)
    """

    context_window: int | None = None
    max_output_tokens: int | None = None
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None

    def to_model_info(self, model_id: str, provider_id: str) -> ModelInfo:
        """Создаёт ModelInfo из конфигурации модели.

        Args:
            model_id: Идентификатор модели (например, "gpt-4o")
            provider_id: Идентификатор провайдера (например, "openai")

        Returns:
            ModelInfo с метаданными модели
        """
        return ModelInfo(
            id=model_id,
            provider_id=provider_id,
            name=_humanize_name(model_id),
            context_window=self.context_window,
            max_output_tokens=self.max_output_tokens,
            cost_per_input_token=self.cost_per_input_token,
            cost_per_output_token=self.cost_per_output_token,
        )


class ProviderConfig(BaseModel):
    """Конфигурация провайдера.

    Атрибуты:
        api_key: API ключ (поддерживает ${ENV_VAR} expansion)
        base_url: Base URL API
        default_model: Модель по умолчанию
        models: Per-model конфигурация
    """

    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    models: dict[str, ModelConfig] = Field(default_factory=dict)

    @field_validator("api_key", mode="before")
    @classmethod
    def expand_env_in_api_key(cls, v: str | None) -> str | None:
        """Раскрывает переменные окружения в api_key."""
        if v and isinstance(v, str):
            return _expand_env_vars(v)
        return v

    def to_provider_info(self, provider_id: str) -> ProviderInfo:
        """Создаёт ProviderInfo из конфигурации провайдера.

        Args:
            provider_id: Идентификатор провайдера (например, "openai")

        Returns:
            ProviderInfo со списком моделей
        """
        models = [
            model_cfg.to_model_info(model_id, provider_id)
            for model_id, model_cfg in self.models.items()
        ]
        return ProviderInfo(
            id=provider_id,
            name=provider_id.title(),
            base_url=self.base_url,
            models=models,
        )


class FallbackConfig(BaseModel):
    """Конфигурация fallback системы.

    Атрибуты:
        enabled: Включён ли fallback
        strategy: Стратегия (sequential, cost, latency, smart)
        order: Порядок провайдеров
        max_attempts: Максимальное количество попыток
        retry_on: Типы ошибок для retry
    """

    enabled: bool = False
    strategy: str = "sequential"
    order: list[str] = Field(default_factory=list)
    max_attempts: int = 3
    retry_on: list[str] = Field(default_factory=lambda: ["rate_limit", "timeout"])


class LLMSectionConfig(BaseModel):
    """Конфигурация LLM секции в TOML.

    Атрибуты:
        provider: Активный провайдер
        model: Активная модель
        temperature: Температура генерации
        max_tokens: Максимальное количество токенов
        providers: Конфигурация провайдеров
        fallback: Конфигурация fallback
    """

    provider: str = "mock"
    model: str = "mock-model"
    temperature: float = 0.7
    max_tokens: int = 8192
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    fallback: FallbackConfig = Field(default_factory=FallbackConfig)


class TOMLConfig(BaseSettings):
    """Корневая конфигурация TOML файла.

    TOML структура имеет [llm] секцию, поэтому этот класс
    содержит одно поле `llm` типа LLMSectionConfig.
    """

    llm: LLMSectionConfig = Field(default_factory=LLMSectionConfig)

    model_config = SettingsConfigDict(
        env_prefix="CODELAB_",
        extra="ignore",
    )

    @property
    def llm_provider(self) -> str:
        """Активный LLM провайдер."""
        return self.llm.provider

    @property
    def llm_model(self) -> str:
        """Активная LLM модель."""
        return self.llm.model

    @property
    def temperature(self) -> float:
        """Температура генерации."""
        return self.llm.temperature

    @property
    def max_tokens(self) -> int:
        """Максимальное количество токенов."""
        return self.llm.max_tokens

    @property
    def providers(self) -> dict[str, ProviderConfig]:
        """Конфигурация провайдеров."""
        return self.llm.providers

    @property
    def fallback(self) -> FallbackConfig:
        """Конфигурация fallback."""
        return self.llm.fallback

    @classmethod
    def from_toml_file(cls, path: Path | str | None = None) -> TOMLConfig:
        """Создаёт конфигурацию из TOML файла.

        Args:
            path: Путь к TOML файлу. Если None, ищет codelab.toml в cwd.

        Returns:
            TOMLConfig с загруженной конфигурацией
        """
        if path is None:
            path = Path.cwd() / "codelab.toml"

        toml_path = Path(path) if isinstance(path, str) else path

        if not toml_path.exists():
            # Если файл не найден, создаём с пустыми providers
            return cls()

        # Создаём подкласс с динамическим toml_file
        class TOMLConfigWithFile(cls):
            model_config = SettingsConfigDict(
                env_prefix="CODELAB_",
                toml_file=str(toml_path),
                extra="ignore",
            )

            @classmethod
            def settings_customise_sources(
                cls,
                settings_cls: type[BaseSettings],
                init_settings: PydanticBaseSettingsSource,
                env_settings: PydanticBaseSettingsSource,
                dotenv_settings: PydanticBaseSettingsSource,
                file_secret_settings: PydanticBaseSettingsSource,
            ) -> tuple[PydanticBaseSettingsSource, ...]:
                toml_settings = TomlConfigSettingsSource(settings_cls)
                return (
                    init_settings,
                    env_settings,
                    dotenv_settings,
                    file_secret_settings,
                    toml_settings,
                )

        return TOMLConfigWithFile()
