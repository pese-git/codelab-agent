# CodeLab

> AI-ассистент для разработчиков с открытой архитектурой и полным контролем над действиями агента.

## Что такое CodeLab?

CodeLab — AI-ассистент для разработчиков, который работает с вашим кодом: читает файлы, выполняет команды, создаёт и редактирует код — из терминала или IDE. Все действия проходят через систему разрешений — вы контролируете каждое изменение агента.

Проект объединяет:

- **ACP-сервер** — интеллектуальный агент с поддержкой 8+ LLM провайдеров (OpenAI, Anthropic, OpenRouter, Zen, Go, Ollama, LMStudio, Mock)
- **TUI-клиент** — терминальный интерфейс на базе Textual
- **Web UI** — браузерный интерфейс для удаленной работы
- **stdio транспорт** — основной транспорт ACP (stdin/stdout JSON-RPC)
- **MCP интеграция** — подключение внешних инструментов через Model Context Protocol

## Быстрый старт

```bash
# Установка зависимостей
cd codelab && uv sync

# Локальный режим (stdio транспорт, сервер как subprocess)
uv run codelab

# Или сервер + клиент отдельно
uv run codelab serve --port 8080        # WebSocket сервер
uv run codelab connect --port 8080      # TUI клиент

# stdio транспорт (для IDE plugins)
uv run codelab serve --stdio            # сервер в stdio режиме
uv run codelab connect --stdio          # клиент запускает агент как subprocess
```

## Документация

| Раздел | Описание |
|--------|----------|
| [Введение](doc/product/overview/01-introduction.md) | Обзор возможностей и архитектуры |
| [Быстрый старт](doc/product/getting-started/03-quickstart.md) | Пошаговая инструкция запуска |
| [Руководство пользователя](doc/product/user-guide/01-tui-client.md) | Работа с TUI-клиентом |
| [Руководство разработчика](doc/product/developer-guide/01-architecture.md) | Архитектура и разработка |
| [Справочник CLI](doc/product/reference/01-cli.md) | Команды и опции |
| [Архитектура](doc/internals/architecture/ARCHITECTURE.md) | Детальная архитектура системы |
| [ACP Protocol](doc/protocols/Agent%20Client%20Protocol/) | Официальная спецификация протокола |

## Структура проекта

```
codelab-agent/
├── codelab/                    # Основной Python-пакет
│   ├── src/codelab/
│   │   ├── client/             # ACP-клиент (Clean Architecture)
│   │   │   ├── domain/         # Сущности и интерфейсы
│   │   │   ├── application/    # Use Cases, State Machine
│   │   │   ├── infrastructure/ # DI, Transport, Handlers
│   │   │   ├── presentation/   # ViewModels (MVVM, 14 штук)
│   │   │   └── tui/            # Textual UI компоненты
│   │   ├── server/             # ACP-сервер
│   │   │   ├── protocol/       # Обработчики методов ACP + Pipeline
│   │   │   ├── agent/          # LLM-агент (ExecutionEngine, AgentLoop)
│   │   │   ├── tools/          # Инструменты (fs, terminal, plan)
│   │   │   ├── storage/        # Хранилище сессий
│   │   │   ├── llm/            # LLM-провайдеры (8+)
│   │   │   ├── mcp/            # MCP интеграция (Manager, Client, Adapters)
│   │   │   └── observability/  # Tracing, Metrics, Timeline
│   │   ├── shared/             # Общие модули (messages, logging, content)
│   │   └── cli.py              # CLI точка входа
│   └── tests/                  # Тесты (~3300 тестов)
├── doc/
│   ├── product/                # Продуктовая документация (для website)
│   │   ├── overview/           # Введение, архитектура, сценарии
│   │   ├── getting-started/    # Установка, быстрый старт
│   │   ├── user-guide/         # Руководство пользователя
│   │   ├── developer-guide/    # Для разработчиков
│   │   ├── reference/          # Справочники (CLI, config, env)
│   │   └── support/            # FAQ, troubleshooting
│   ├── protocols/              # Референсные протоколы (не изменять!)
│   │   ├── Agent Client Protocol/
│   │   ├── Agent To Agent Protocol/
│   │   └── Model Context Protocol/
│   └── internals/              # Внутренние документы
│       ├── architecture/       # Архитектура, ADR, карта проекта
│       ├── roadmap/            # Планы развития кодовой базы
│       └── archive/            # Исторические документы
└── Makefile                    # Команды сборки и проверок
```

## Проверки

```bash
# Полный набор проверок
make check

# Или вручную
cd codelab
uv run ruff check .
uv run ty check
uv run python -m pytest
```

## Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — менеджер пакетов

## Лицензия

MIT License
