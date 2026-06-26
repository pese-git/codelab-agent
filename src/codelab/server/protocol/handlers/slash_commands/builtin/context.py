"""Handler для команды /context.

Показывает состояние Context Manager: метрики, span'ы, конфигурацию.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from codelab.server.models import AvailableCommand, AvailableCommandInput

from ..base import CommandHandler, CommandResult

if TYPE_CHECKING:
    from codelab.server.agent.context.models import ContextConfig
    from codelab.server.observability.metrics_tracker import MetricsTracker
    from codelab.server.observability.tracer import SpanContext, Tracer
    from codelab.server.protocol.state import SessionState


class ContextCommandHandler(CommandHandler):
    """Handler для команды /context.

    Без аргументов: показывает сводку метрик Context Manager.
    /context spans: показывает последние span'ы context.build и context.gather.
    /context on|off: включает/выключает Context Manager.

    Пример использования:
        handler = ContextCommandHandler(metrics_tracker, tracer)
        result = handler.execute([], session)
    """

    def __init__(
        self,
        metrics_tracker: MetricsTracker,
        config: ContextConfig,
        tracer: Tracer | None = None,
    ) -> None:
        """Инициализация handler.

        Args:
            metrics_tracker: MetricsTracker для получения метрик
            config: ContextConfig с настройками Context Manager
            tracer: Tracer для получения span'ов (опционально)
        """
        self._metrics_tracker = metrics_tracker
        self._config = config
        self._tracer = tracer

    def execute(
        self,
        args: list[str],
        session: SessionState,
    ) -> CommandResult:
        """Выполняет команду /context.

        Args:
            args: Аргументы команды (пусто, "spans", "on", "off")
            session: Состояние сессии

        Returns:
            CommandResult с информацией о контексте
        """
        if not args:
            return self._show_summary(session)

        subcommand = args[0].lower()

        if subcommand == "spans":
            return self._show_spans(session)

        if subcommand == "on":
            return self._set_enabled(session, True)

        if subcommand == "off":
            return self._set_enabled(session, False)

        return CommandResult(
            content=[{
                "type": "text",
                "text": (
                    "❌ Неизвестная подкоманда: `/context {subcommand}`\n\n"
                    "Доступные:\n"
                    "• `/context` — сводка метрик\n"
                    "• `/context spans` — последние span'ы\n"
                    "• `/context on` — включить Context Manager\n"
                    "• `/context off` — выключить Context Manager"
                ),
            }]
        )

    def _show_summary(self, session: SessionState) -> CommandResult:
        """Показать сводку метрик Context Manager."""
        session_id = session.session_id
        metrics = self._metrics_tracker.get_metrics(session_id)

        # Runtime override из session имеет приоритет над конфигом
        session_enabled = session.config_values.get("context_enabled")
        if session_enabled is not None:
            context_enabled = session_enabled == "true"
        else:
            context_enabled = self._config.enabled

        session_gather = session.config_values.get("context_gather_enabled")
        if session_gather is not None:
            gather_enabled = session_gather == "true"
        else:
            gather_enabled = self._config.gather_enabled

        status_icon = "✅" if context_enabled else "⏸️"
        gather_status = "on" if gather_enabled else "off"

        lines = [
            f"📦 **Context Manager** {status_icon}",
            "",
            f"**Статус:** `enabled={context_enabled}`, `gather={gather_status}`",
            "",
        ]

        # Метрики сессии
        if metrics.context_build_count > 0:
            avg_build_ms = metrics.context_build_total_ms / metrics.context_build_count
            lines.extend([
                "**Метрики сессии:**",
                f"• Сборок контекста: `{metrics.context_build_count}`",
                f"• Среднее время сборки: `{avg_build_ms:.1f}ms`",
                f"• Собрано файлов: `{metrics.context_gathered_files}`",
                f"• Baseline токенов: `{metrics.context_baseline_tokens:,}`",
                f"• Tail токенов: `{metrics.context_tail_tokens:,}`",
            ])
        else:
            lines.append("**Метрики:** нет данных (сборок не было)")

        # Последние сборки (из debug деталей)
        if self._metrics_tracker.debug and metrics.context_build_details:
            lines.extend(["", "**Последние сборки:**"])
            recent = metrics.context_build_details[-5:]
            for i, detail in enumerate(reversed(recent), 1):
                duration = detail.get("build_duration_ms", 0)
                files = detail.get("gathered_files", 0)
                baseline = detail.get("baseline_tokens", 0)
                lines.append(f"  {i}. `{duration:.0f}ms`, {files} файлов, {baseline:,} токенов")

        lines.extend([
            "",
            "Для span'ов: `/context spans`",
            "Для управления: `/context on|off`",
        ])

        return CommandResult(content=[{"type": "text", "text": "\n".join(lines)}])

    def _show_spans(self, session: SessionState) -> CommandResult:
        """Показать последние span'ы context.build и context.gather.

        Использует комбинированный подход:
        1. Сначала проверяет память (актуальные span'ы)
        2. Если пусто — читает из последнего экспортированного файла
        """
        if self._tracer is None:
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": "⚠️ Tracer не инициализирован. Span'ы недоступны.",
                }]
            )

        session_id = session.session_id
        source = "memory"

        # 1. Сначала проверяем память (актуальные span'ы)
        completed = self._tracer.get_completed_spans(session_id=session_id)
        context_spans = [
            s for s in completed
            if s.name.startswith("context.")
        ]

        # 2. Если пусто — читаем из последнего экспортированного файла
        if not context_spans:
            context_spans = self._load_spans_from_latest_file(session_id)
            source = "file"

        if not context_spans:
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": "📭 Нет span'ов контекста для этой сессии.",
                }]
            )

        # Берём последние 10
        recent = context_spans[-10:]

        lines = [
            f"🔍 **Последние span'ы контекста** (источник: {source}):",
            "",
        ]

        for span in recent:
            duration = span.duration_ms or 0
            attrs = span.attributes

            if span.name == "context.build":
                agent_scope = attrs.get("agent_scope", "?")
                task_type = attrs.get("task_type", "?")
                files = attrs.get("gathered_files", 0)
                baseline_tokens = attrs.get("baseline_tokens", 0)
                lines.append(
                    f"• **context.build** — `{duration:.0f}ms` | "
                    f"scope: `{agent_scope}`, task: `{task_type}`, "
                    f"files: `{files}`, tokens: `{baseline_tokens:,}`"
                )
            elif span.name == "context.gather":
                task_type = attrs.get("task_type", "?")
                candidates = attrs.get("candidate_files", 0)
                selected = attrs.get("selected_files", 0)
                lines.append(
                    f"• **context.gather** — `{duration:.0f}ms` | "
                    f"task: `{task_type}`, "
                    f"candidates: `{candidates}`, selected: `{selected}`"
                )
            else:
                lines.append(f"• **{span.name}** — `{duration:.0f}ms`")

        return CommandResult(content=[{"type": "text", "text": "\n".join(lines)}])

    def _load_spans_from_latest_file(self, session_id: str) -> list[SpanContext]:
        """Загрузить span'ы из последнего экспортированного файла.

        Args:
            session_id: ID сессии для фильтрации

        Returns:
            Список SpanContext из файла или пустой список
        """
        from codelab.server.observability.tracer import SpanContext

        spans_dir = Path.home() / ".codelab" / "data" / "observability" / "spans"
        if not spans_dir.exists():
            return []

        # Находим последний файл
        span_files = sorted(spans_dir.glob("*.json"), reverse=True)
        if not span_files:
            return []

        latest_file = span_files[0]

        try:
            with open(latest_file, encoding="utf-8") as f:
                data = json.load(f)

            # Фильтруем span'ы по session_id и имени
            context_spans = []
            for span_data in data:
                if (
                    span_data.get("session_id") == session_id
                    and span_data.get("name", "").startswith("context.")
                ):
                    span = SpanContext(
                        span_id=span_data.get("span_id", ""),
                        name=span_data.get("name", ""),
                        parent_id=span_data.get("parent_id"),
                        attributes=span_data.get("attributes", {}),
                        start_time=span_data.get("start_time", 0),
                        end_time=span_data.get("end_time"),
                        session_id=span_data.get("session_id", ""),
                    )
                    context_spans.append(span)

            return context_spans
        except Exception:
            return []

    def _get_effective_enabled(self, session: SessionState) -> bool:
        """Получить эффективный статус Context Manager (конфиг + runtime override)."""
        session_enabled = session.config_values.get("context_enabled")
        if session_enabled is not None:
            return session_enabled == "true"
        return self._config.enabled

    def _set_enabled(self, session: SessionState, enabled: bool) -> CommandResult:
        """Включить или выключить Context Manager."""
        current = self._get_effective_enabled(session)

        if current == enabled:
            state = "включён" if enabled else "выключен"
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": f"ℹ️ Context Manager уже {state}.",
                }]
            )

        session.config_values["context_enabled"] = "true" if enabled else "false"

        action = "включён" if enabled else "выключен"
        return CommandResult(
            content=[{
                "type": "text",
                "text": f"✅ Context Manager {action}.",
            }]
        )

    def get_definition(self) -> AvailableCommand:
        """Возвращает определение команды /context."""
        return AvailableCommand(
            name="context",
            description="Показать состояние Context Manager",
            input=AvailableCommandInput(hint="spans | on | off"),
        )
