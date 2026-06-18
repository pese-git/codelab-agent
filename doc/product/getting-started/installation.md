# Установка

> Пошаговая инструкция по установке CodeLab.

## Быстрая установка

```bash
# 1. Клонирование репозитория
git clone https://github.com/pese-git/codelab-agent.git
cd codelab-agent/codelab

# 2. Установка зависимостей
uv sync

# 3. Проверка установки
uv run codelab --help
```

## Варианты установки

CodeLab поддерживает несколько конфигураций через optional dependencies.

### Базовая установка

Минимальная установка для разработки:

```bash
uv sync
```

### С поддержкой LLM-сервера

Для работы с реальными LLM (OpenAI, Anthropic):

```bash
uv sync --extra server
```

### С TUI-клиентом

Для терминального интерфейса:

```bash
uv sync --extra tui
```

### С Web UI

Для браузерного интерфейса:

```bash
uv sync --extra web
```

### Полная установка

Все компоненты:

```bash
uv sync --extra full
```

### Для разработки

Включает инструменты разработки (pytest, ruff, ty):

```bash
uv sync --extra dev
```

## Конфигурация

### Создание файла конфигурации

```bash
# Копирование примера
cp .env.example .env

# Редактирование
nano .env  # или используйте любой редактор
```

### Основные переменные окружения

```bash
# .env файл

# LLM провайдер (openai, anthropic, openrouter, zen, go, ollama, lmstudio, mock)
CODELAB_LLM_PROVIDER=openai

# Модель LLM в формате "provider/model"
CODELAB_LLM_MODEL=openai/gpt-4o

# API ключи
OPENAI_API_KEY=sk-your-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Порт сервера
CODELAB_PORT=8765

# Хост сервера
CODELAB_HOST=127.0.0.1

# Уровень логирования (DEBUG, INFO, WARNING, ERROR)
CODELAB_LOG_LEVEL=INFO
```

### Таблица конфигурации

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `CODELAB_LLM_PROVIDER` | Активный провайдер LLM | `mock` |
| `CODELAB_LLM_MODEL` | Модель в формате `"provider/model"` | `mock/mock-model` |
| `OPENAI_API_KEY` | API ключ OpenAI | — |
| `ANTHROPIC_API_KEY` | API ключ Anthropic | — |
| `OPENROUTER_API_KEY` | API ключ OpenRouter | — |
| `CODELAB_FALLBACK_ENABLED` | Включить fallback | `false` |
| `CODELAB_FALLBACK_ORDER` | Порядок fallback провайдеров | — |
| `CODELAB_PORT` | Порт сервера | `8765` |
| `CODELAB_HOST` | Хост сервера | `127.0.0.1` |
| `CODELAB_LOG_LEVEL` | Уровень логов | `INFO` |

## Домашняя директория

При первом запуске создаётся структура в `~/.codelab/`:

```
~/.codelab/
├── config/   # Конфигурационные файлы
├── logs/     # Файлы логов (codelab.log)
├── data/     # Сессии, история
└── cache/    # Кэш MCP и временные данные
```

## Проверка установки

### Проверка CLI

```bash
uv run codelab --help
```

Ожидаемый вывод:
```
Usage: codelab [OPTIONS] COMMAND [ARGS]...

  CodeLab - AI-powered coding assistant

Commands:
  serve    Start the ACP server
  connect  Connect TUI client to server
```

### Проверка сервера

```bash
uv run codelab serve --port 8765
```

Ожидаемый вывод:
```
INFO     starting_server_mode host=127.0.0.1 port=8765 enable_web=True
INFO     endpoints_available ws_api=ws://127.0.0.1:8765/acp/ws web_ui=http://127.0.0.1:8765/
```

## Обновление

```bash
# Получение обновлений
cd codelab-agent
git pull origin main

# Переустановка зависимостей
cd codelab
uv sync
```

## Удаление

```bash
# Удаление репозитория
rm -rf codelab-agent

# Удаление домашней директории (опционально)
rm -rf ~/.codelab
```

## Решение проблем

### Ошибка "uv: command not found"

```bash
# Переустановка uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # или ~/.zshrc
```

### Ошибка "Python 3.12 required"

```bash
# macOS
brew install python@3.12

# Ubuntu
sudo apt install python3.12
```

### Ошибка при uv sync

```bash
# Очистка кэша и повторная установка
uv cache clean
uv sync --reinstall
```

### Порт уже занят

```bash
# Проверка занятости порта
lsof -i :8765

# Использование другого порта
uv run codelab serve --port 8766
```

## Следующие шаги

- [Быстрый старт](quickstart.md) — первый запуск и основы работы
- [Первый проект](first-project.md) — практический пример
- [Интеграция с Zed IDE](../user-guide/ide/zed-ide-integration.md) — настройка в Zed IDE
