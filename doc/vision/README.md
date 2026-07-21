# Vision / Roadmap

Стратегическое видение развития CodeLab Agent.

> Эти документы описывают **целевую архитектуру** системы уровня Claude Code / Cursor,
> а не текущее состояние реализации.

## Содержание

### System Architecture

Полная архитектура системы, разделённая по функциональным слоям:

- **[SYSTEM_ARCHITECTURE.md](system-architecture/SYSTEM_ARCHITECTURE.md)** — обзорная диаграмма, 5-уровневая модель зрелости
- **[CONTEXT_LIFECYCLE.md](system-architecture/CONTEXT_LIFECYCLE.md)** — жизненный цикл контекста (эпохи, снапшоты)
- **[SEMANTIC_LAYER.md](system-architecture/SEMANTIC_LAYER.md)** — векторные индексы, RAG, semantic search
- **[PLANNING_ENGINE.md](system-architecture/PLANNING_ENGINE.md)** — LLM-based планирование изменений
- **[VERIFICATION_LAYER.md](system-architecture/VERIFICATION_LAYER.md)** — верификация (тесты, сборка, lint)
- **[MEMORY_LAYER.md](system-architecture/MEMORY_LAYER.md)** — память между сессиями
- **[LSP_INTEGRATION.md](system-architecture/LSP_INTEGRATION.md)** — Language Server Protocol
- **[GIT_AWARENESS.md](system-architecture/GIT_AWARENESS.md)** — Git-контекст (branch, diff, blame)
- **[FILE_INTELLIGENCE.md](system-architecture/FILE_INTELLIGENCE.md)** — интеллектуальный анализ файлов
- **[CODE_UNDERSTANDING.md](system-architecture/CODE_UNDERSTANDING.md)** — AST, символьный анализ
- **[DISCOVERY_LAYER.md](system-architecture/DISCOVERY_LAYER.md)** — умный поиск файлов
- **[AUTONOMOUS_REASONING.md](system-architecture/AUTONOMOUS_REASONING.md)** — саморефлексия, recovery

## Статус реализации

| Уровень | Описание | Статус |
|---|---|---|
| Level 1 (Core) | ExecutionEngine, ContextManager, TaskAnalyzer | Реализовано |
| Level 2 (Advanced) | DependencyGraph, SymbolResolver | Частично |
| Level 3 (Production) | Git, Verification, Memory | Частично |
| Level 4 (Claude Code) | Planning, Subagents | Не реализовано |
| Level 5 (Ultimate) | Semantic Layer, LSP | Не реализовано |

## Использование

Эти документы служат:
- Roadmap развития продукта
- Обоснование архитектурных решений
- Сравнение с конкурентами (Claude Code, Cursor, OpenCode)
