"""ContextRegistry и реализации ContextSource.

ContextRegistry управляет источниками контекста и отслеживает изменения.
ContextSource — абстракция для различных источников (файлы, скиллы, и т.д.).

Слой A — Сбор контекста (Phase 1).
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import structlog

from codelab.server.agent.context.interfaces import ContextRegistry, ContextSource

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class FileContextSource(ContextSource):
    """Источник контекста на основе файла."""

    def __init__(self, path: str, content: str) -> None:
        self._path = path
        self._content = content

    @property
    def source_id(self) -> str:
        """Уникальный идентификатор — путь к файлу."""
        return self._path

    async def render(self) -> str:
        """Отрендерить содержимое файла."""
        return self._content

    async def fingerprint(self) -> str:
        """Вычислить fingerprint на основе содержимого."""
        return hashlib.sha256(self._content.encode()).hexdigest()[:16]


class SkillContextSource(ContextSource):
    """Источник контекста на основе skill/инструкции."""

    def __init__(self, skill_id: str, content: str) -> None:
        self._skill_id = skill_id
        self._content = content

    @property
    def source_id(self) -> str:
        """Уникальный идентификатор — ID скилла."""
        return f"skill:{self._skill_id}"

    async def render(self) -> str:
        """Отрендерить содержимое скилла."""
        return self._content

    async def fingerprint(self) -> str:
        """Вычислить fingerprint на основе содержимого."""
        return hashlib.sha256(self._content.encode()).hexdigest()[:16]


class ContextRegistryImpl(ContextRegistry):
    """Реестр источников контекста с отслеживанием изменений."""

    def __init__(self) -> None:
        self._sources: dict[str, ContextSource] = {}
        self._last_fingerprints: dict[str, str] = {}

    def register(self, source: ContextSource) -> None:
        """Зарегистрировать источник контекста."""
        self._sources[source.source_id] = source
        logger.debug(
            "context_registry.source_registered",
            source_id=source.source_id,
            total_sources=len(self._sources),
        )

    def unregister(self, source_id: str) -> None:
        """Удалить источник из реестра."""
        if source_id in self._sources:
            del self._sources[source_id]
            logger.debug(
                "context_registry.source_unregistered",
                source_id=source_id,
                total_sources=len(self._sources),
            )

    async def render_baseline(self) -> str:
        """Отрендерить все источники для baseline."""
        parts: list[str] = []
        for _source_id, source in self._sources.items():
            content = await source.render()
            if content:
                parts.append(content)

        baseline = "\n\n".join(parts)
        logger.debug(
            "context_registry.baseline_rendered",
            sources_count=len(self._sources),
            baseline_length=len(baseline),
        )
        return baseline

    async def render_updates(self, changes: list[str]) -> str:
        """Отрендерить только изменённые источники."""
        parts: list[str] = []
        for source_id in changes:
            if source_id in self._sources:
                source = self._sources[source_id]
                content = await source.render()
                if content:
                    parts.append(content)

        updates = "\n\n".join(parts)
        logger.debug(
            "context_registry.updates_rendered",
            changed_sources=len(changes),
            updates_length=len(updates),
        )
        return updates

    async def detect_changes(self) -> list[str]:
        """Обнаружить изменённые источники с момента последнего снимка."""
        changed: list[str] = []

        for source_id, source in self._sources.items():
            current_fp = await source.fingerprint()
            last_fp = self._last_fingerprints.get(source_id)

            if last_fp is None or last_fp != current_fp:
                changed.append(source_id)
                self._last_fingerprints[source_id] = current_fp

        # Удалить fingerprint'ы для удалённых источников
        current_ids = set(self._sources.keys())
        for old_id in list(self._last_fingerprints.keys()):
            if old_id not in current_ids:
                del self._last_fingerprints[old_id]

        logger.debug(
            "context_registry.changes_detected",
            changed_sources=len(changed),
            total_sources=len(self._sources),
        )
        return changed

    async def snapshot(self) -> dict[str, str]:
        """Создать снимок fingerprint'ов всех источников."""
        fingerprints: dict[str, str] = {}
        for source_id, source in self._sources.items():
            fingerprints[source_id] = await source.fingerprint()

        self._last_fingerprints = fingerprints.copy()
        return fingerprints

    def get_source(self, source_id: str) -> ContextSource | None:
        """Получить источник по ID."""
        return self._sources.get(source_id)

    def list_sources(self) -> list[str]:
        """Получить список ID всех зарегистрированных источников."""
        return list(self._sources.keys())
