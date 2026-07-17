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

    Подкоманды:
    - (без аргументов): расширенная сводка метрик (Контекст, LLM, Агент)
    - config: полная конфигурация ContextConfig с budget allocation
    - last: детали последней сборки (stage timings, files, tokens)
    - files: список собранных файлов с токенами
    - graph: статистика графа зависимостей
    - profile: последний профиль задачи
    - spans: последние span'ы context.build и context.gather
    - on|off: включить/выключить Context Manager
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
            args: Аргументы команды (пусто, "config", "last", "files", "graph",
                "profile", "spans", "on", "off")
            session: Состояние сессии

        Returns:
            CommandResult с информацией о контексте
        """
        if not args:
            return self._show_summary(session)

        subcommand = args[0].lower()

        if subcommand == "spans":
            return self._show_spans(session)

        if subcommand == "config":
            return self._show_config(session)

        if subcommand == "last":
            return self._show_last(session)

        if subcommand == "files":
            return self._show_files(session)

        if subcommand == "graph":
            return self._show_graph(session)

        if subcommand == "profile":
            return self._show_profile(session)

        if subcommand == "on":
            return self._set_enabled(session, True)

        if subcommand == "off":
            return self._set_enabled(session, False)

        return CommandResult(
            content=[
                {
                    "type": "text",
                    "text": (
                        f"❌ Неизвестная подкоманда: `/context {subcommand}`\n\n"
                        "Доступные:\n"
                        "• `/context` — расширенная сводка (Контекст, LLM, Агент)\n"
                        "• `/context config` — полная конфигурация\n"
                        "• `/context last` — детали последней сборки\n"
                        "• `/context files` — список собранных файлов\n"
                        "• `/context graph` — статистика графа зависимостей\n"
                        "• `/context profile` — последний профиль задачи\n"
                        "• `/context spans` — последние span'ы\n"
                        "• `/context on` — включить Context Manager\n"
                        "• `/context off` — выключить Context Manager"
                    ),
                }
            ]
        )

    def _show_summary(self, session: SessionState) -> CommandResult:
        """Показать расширенную сводку метрик Context Manager."""
        session_id = session.session_id
        metrics = self._metrics_tracker.get_metrics(session_id)

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

        # Секция: Контекст
        if metrics.context_build_count > 0:
            avg_build_ms = metrics.context_build_total_ms / metrics.context_build_count
            lines.extend(
                [
                    "**Контекст:**",
                    f"• Сборок: `{metrics.context_build_count}`",
                    f"• Среднее время: `{avg_build_ms:.1f}ms`",
                    f"• Собрано файлов: `{metrics.context_gathered_files}`",
                    f"• Baseline токенов: `{metrics.context_baseline_tokens:,}`",
                    f"• Tail токенов: `{metrics.context_tail_tokens:,}`",
                ]
            )
        else:
            lines.append("**Контекст:** нет данных (сборок не было)")

        # Секция: LLM
        lines.append("")
        if metrics.llm_call_count > 0:
            lines.extend(
                [
                    "**LLM:**",
                    f"• Вызовов: `{metrics.llm_call_count}`",
                    f"• Input tokens: `{metrics.llm_total_input_tokens:,}`",
                    f"• Output tokens: `{metrics.llm_total_output_tokens:,}`",
                ]
            )
        else:
            lines.append("**LLM:** нет данных (вызовов не было)")

        # Секция: Агент
        lines.append("")
        if metrics.agent_responses > 0:
            lines.extend(
                [
                    "**Агент:**",
                    f"• Ответов: `{metrics.agent_responses}`",
                    f"• Ошибок: `{metrics.agent_errors}`",
                ]
            )
        else:
            lines.append("**Агент:** нет данных (ответов не было)")

        # Подсказки
        lines.extend(
            [
                "",
                "Для конфигурации: `/context config`",
                "Для деталей: `/context last`",
                "Для файлов: `/context files`",
                "Для графа: `/context graph`",
                "Для профиля: `/context profile`",
                "Для span'ов: `/context spans`",
                "Для управления: `/context on|off`",
            ]
        )

        return CommandResult(content=[{"type": "text", "text": "\n".join(lines)}])

    def _show_config(self, session: SessionState) -> CommandResult:
        """Показать полную конфигурацию Context Manager."""
        max_tokens = self._config.max_context_tokens

        lines = [
            "📋 **Конфигурация Context Manager:**",
            "",
            "**Общие:**",
            f"• enabled: `{self._config.enabled}`",
            f"• gather_enabled: `{self._config.gather_enabled}`",
            f"• incremental: `{self._config.incremental}`",
            f"• federation: `{self._config.federation}`",
            "",
            "**Анализ:**",
            f"• analyzer_model: `{self._config.analyzer_model}`",
            f"• recursive_dependencies: `{self._config.recursive_dependencies}`",
            "",
            "**Оптимизация:**",
            f"• use_tree_sitter: `{self._config.use_tree_sitter}`",
            f"• use_tiktoken: `{self._config.use_tiktoken}`",
            f"• file_cache: `{self._config.file_cache}` "
            f"(max: `{self._config.cache_max_files:,}` файлов)",
            f"• skeletonize: `{self._config.skeletonize}`",
            "",
            "**Бюджет:**",
            f"• max_context_tokens: `{max_tokens:,}`",
            f"• reserved_tokens: `{self._config.reserved_tokens:,}`",
        ]

        system_tokens = int(max_tokens * self._config.system_share)
        history_tokens = int(max_tokens * self._config.history_share)
        tool_tokens = int(max_tokens * self._config.tool_output_share)
        buffer_tokens = int(max_tokens * self._config.response_buffer_share)

        lines.extend(
            [
                f"• system: `{int(self._config.system_share * 100)}%` → `{system_tokens:,} tokens`",
                f"• history: `{int(self._config.history_share * 100)}%` → "
                f"`{history_tokens:,} tokens`",
                f"• tool_output: `{int(self._config.tool_output_share * 100)}%` → "
                f"`{tool_tokens:,} tokens`",
                f"• response_buffer: "
                f"`{int(self._config.response_buffer_share * 100)}%` → "
                f"`{buffer_tokens:,} tokens`",
            ]
        )

        # Runtime overrides
        overrides = {k: v for k, v in session.config_values.items() if k.startswith("context_")}
        if overrides:
            lines.extend(["", "**Runtime overrides:**"])
            for key, value in sorted(overrides.items()):
                lines.append(f"• {key}: `{value}`")

        return CommandResult(content=[{"type": "text", "text": "\n".join(lines)}])

    def _show_last(self, session: SessionState) -> CommandResult:
        """Показать детали последней сборки контекста."""
        metrics = self._metrics_tracker.get_metrics(session.session_id)

        if not metrics.context_build_details:
            return CommandResult(
                content=[
                    {
                        "type": "text",
                        "text": "📭 Детали недоступны. Сборок контекста ещё не было.",
                    }
                ]
            )

        last = metrics.context_build_details[-1]
        stage_timings = last.get("stage_timings", {})
        graph_stats = last.get("graph_stats", {})
        file_paths = last.get("file_paths", [])
        file_tokens = last.get("file_tokens", [])
        fingerprint = last.get("fingerprint", "")

        lines = [
            "🔬 **Последняя сборка контекста:**",
            "",
            "**Общее:**",
            f"• Длительность: `{last.get('build_duration_ms', 0):.0f}ms`",
            f"• task_type: `{last.get('task_type', '?')}`",
            f"• fingerprint: `{fingerprint or '—'}`",
        ]

        if stage_timings:
            lines.extend(["", "**Стадии:**"])
            for stage in (
                "extract_ms",
                "analyze_ms",
                "gather_ms",
                "baseline_ms",
                "tail_ms",
                "fingerprint_ms",
            ):
                name = stage.replace("_ms", "")
                lines.append(f"• {name}: `{stage_timings.get(stage, 0):.0f}ms`")

        lines.extend(
            [
                "",
                "**Файлы:**",
                f"• selected: `{last.get('gathered_files', 0)}`",
                f"• candidates: `{last.get('candidate_count', 0)}`",
            ]
        )

        lines.extend(
            [
                "",
                "**Токены:**",
                f"• baseline: `{last.get('baseline_tokens', 0):,}`",
                f"• tail: `{last.get('tail_tokens', 0):,}`",
            ]
        )

        if graph_stats:
            lines.extend(
                [
                    "",
                    "**Граф зависимостей:**",
                    f"• files_in_graph: `{graph_stats.get('files_in_graph', 0)}`",
                    f"• total_dependencies: `{graph_stats.get('total_dependencies', 0)}`",
                ]
            )

        if file_paths:
            lines.extend(["", f"**Файлы ({len(file_paths)}):**"])
            for i, fp in enumerate(file_paths[:10]):
                tokens = file_tokens[i] if i < len(file_tokens) else None
                suffix = f" — `{tokens:,} tokens`" if tokens is not None else ""
                lines.append(f"• `{fp}`{suffix}")
            if len(file_paths) > 10:
                lines.append(f"• ... и ещё {len(file_paths) - 10}")

        return CommandResult(content=[{"type": "text", "text": "\n".join(lines)}])

    def _show_files(self, session: SessionState) -> CommandResult:
        """Показать список собранных файлов из последней сборки."""
        metrics = self._metrics_tracker.get_metrics(session.session_id)

        if not metrics.context_build_details:
            return CommandResult(
                content=[
                    {
                        "type": "text",
                        "text": "📭 Список файлов недоступен. Сборок контекста ещё не было.",
                    }
                ]
            )

        last = metrics.context_build_details[-1]
        file_paths = last.get("file_paths", [])
        file_tokens = last.get("file_tokens", [])

        if not file_paths:
            return CommandResult(
                content=[
                    {
                        "type": "text",
                        "text": "📭 Файлы не были собраны в последней сборке.",
                    }
                ]
            )

        total_tokens = sum(file_tokens)
        header = f"📁 **Собранные файлы** (последняя сборка, {len(file_paths)} файлов"
        if total_tokens:
            header += f", {total_tokens:,} tokens"
        header += "):"

        lines = [header, ""]
        for i, fp in enumerate(file_paths, 1):
            tokens = file_tokens[i - 1] if i - 1 < len(file_tokens) else None
            suffix = f" — `{tokens:,} tokens`" if tokens is not None else ""
            lines.append(f"{i}. `{fp}`{suffix}")

        return CommandResult(content=[{"type": "text", "text": "\n".join(lines)}])

    def _show_graph(self, session: SessionState) -> CommandResult:
        """Показать статистику графа зависимостей."""
        metrics = self._metrics_tracker.get_metrics(session.session_id)

        if not metrics.context_build_details:
            return CommandResult(
                content=[
                    {
                        "type": "text",
                        "text": "📭 Граф зависимостей не инициализирован (сборок не было).",
                    }
                ]
            )

        last = metrics.context_build_details[-1]
        graph_stats = last.get("graph_stats", {})

        if not graph_stats:
            return CommandResult(
                content=[
                    {
                        "type": "text",
                        "text": "📭 Статистика графа недоступна. Сборок контекста ещё не было.",
                    }
                ]
            )

        lines = [
            "🕸️ **Граф зависимостей:**",
            "",
            f"• files_in_graph: `{graph_stats.get('files_in_graph', 0)}`",
            f"• total_dependencies: `{graph_stats.get('total_dependencies', 0)}`",
            f"• total_dependents: `{graph_stats.get('total_dependents', 0)}`",
            f"• project_files_cached: `{graph_stats.get('project_files_cached', 0)}`",
        ]

        return CommandResult(content=[{"type": "text", "text": "\n".join(lines)}])

    def _show_profile(self, session: SessionState) -> CommandResult:
        """Показать последний профиль задачи."""
        metrics = self._metrics_tracker.get_metrics(session.session_id)
        profile = metrics.last_task_profile

        if profile is None:
            return CommandResult(
                content=[
                    {
                        "type": "text",
                        "text": "📭 Профиль задачи недоступен (сборок не было).",
                    }
                ]
            )

        lines = [
            "🎯 **Последний профиль задачи:**",
            "",
            f"• task_type: `{profile.get('task_type', '?')}`",
            f"• search_terms: `{profile.get('search_terms', [])}`",
            f"• target_modules: `{profile.get('target_modules', [])}`",
            f"• investigation_depth: `{profile.get('investigation_depth', 0)}`",
            f"• needs_tests: `{profile.get('needs_tests', False)}`",
        ]

        return CommandResult(content=[{"type": "text", "text": "\n".join(lines)}])

    def _show_spans(self, session: SessionState) -> CommandResult:
        """Показать последние span'ы context.build и context.gather.

        Использует комбинированный подход:
        1. Сначала проверяет память (актуальные span'ы)
        2. Если пусто — читает из последнего экспортированного файла
        """
        if self._tracer is None:
            return CommandResult(
                content=[
                    {
                        "type": "text",
                        "text": "⚠️ Tracer не инициализирован. Span'ы недоступны.",
                    }
                ]
            )

        session_id = session.session_id
        source = "memory"

        # 1. Сначала проверяем память (актуальные span'ы)
        completed = self._tracer.get_completed_spans(session_id=session_id)
        context_spans = [s for s in completed if s.name.startswith("context.")]

        # 2. Если пусто — читаем из последнего экспортированного файла
        if not context_spans:
            context_spans = self._load_spans_from_latest_file(session_id)
            source = "file"

        if not context_spans:
            return CommandResult(
                content=[
                    {
                        "type": "text",
                        "text": (
                            "📭 Нет span'ов контекста для этой сессии.\n\n"
                            "Возможные причины:\n"
                            "• Context Manager не выполнял сборки (нет LLM-вызовов)\n"
                            "• Span'ы были экспортированы и очищены из памяти\n"
                            "• Observability отключён в конфигурации"
                        ),
                    }
                ]
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
                if span_data.get("session_id") == session_id and span_data.get(
                    "name", ""
                ).startswith("context."):
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
                content=[
                    {
                        "type": "text",
                        "text": f"ℹ️ Context Manager уже {state}.",
                    }
                ]
            )

        session.config_values["context_enabled"] = "true" if enabled else "false"

        action = "включён" if enabled else "выключен"
        return CommandResult(
            content=[
                {
                    "type": "text",
                    "text": f"✅ Context Manager {action}.",
                }
            ]
        )

    def get_definition(self) -> AvailableCommand:
        """Возвращает определение команды /context."""
        return AvailableCommand(
            name="context",
            description="Показать состояние Context Manager",
            input=AvailableCommandInput(
                hint="config | last | files | graph | profile | spans | on | off"
            ),
        )
