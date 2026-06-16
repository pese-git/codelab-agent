# Переменные окружения

Полный справочник переменных окружения CodeLab.

## LLM провайдер

### CODELAB_LLM_PROVIDER

Выбор LLM провайдера.

| Значение | Описание |
|----------|----------|
| `openai` | OpenAI API (GPT-4, GPT-4o, o3, o4-mini) |
| `anthropic` | Anthropic API (Claude Sonnet 4, Opus 4) |
| `openrouter` | OpenRouter (множество моделей) |
| `zen` | Zen API |
| `go` | Go API |
| `ollama` | Локальные модели через Ollama |
| `lmstudio` | Локальные модели через LMStudio |
| `mock` | Тестовый провайдер без реального LLM |

**По умолчанию:** `mock`

```bash
export CODELAB_LLM_PROVIDER=openai
```

### API Keys

Каждый провайдер использует свою переменную окружения для API ключа:

| Провайдер | Переменная |
|-----------|------------|
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |
| Zen | `ZEN_API_KEY` |
| Go | `GO_API_KEY` |
| Ollama | Не требуется |
| LMStudio | Не требуется |

```bash
export OPENAI_API_KEY=sk-your-key-here
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### CODELAB_LLM_MODEL

Название модели LLM в формате `"provider/model"`.

**По умолчанию:** `mock/mock-model`

```bash
# OpenAI модели
export CODELAB_LLM_MODEL=openai/gpt-4o
export CODELAB_LLM_MODEL=openai/o3

# Anthropic модели
export CODELAB_LLM_MODEL=anthropic/claude-sonnet-4
export CODELAB_LLM_MODEL=anthropic/claude-opus-4

# OpenRouter
export CODELAB_LLM_MODEL=openrouter/mistral-large

# Ollama
export CODELAB_LLM_MODEL=ollama/llama3.1:70b
```

### CODELAB_LLM_TEMPERATURE

Параметр "творчества" модели. Значения от 0.0 до 1.0.

- `0.0` — детерминированные ответы
- `0.7` — баланс точности и творчества
- `1.0` — максимальная вариативность

**По умолчанию:** `0.7`

```bash
export CODELAB_LLM_TEMPERATURE=0.3
```

### CODELAB_LLM_MAX_TOKENS

Максимальное количество токенов в ответе модели.

**По умолчанию:** `8192`

```bash
export CODELAB_LLM_MAX_TOKENS=16384
```

## Сервер

### CODELAB_PORT

Порт WebSocket сервера.

**По умолчанию:** `8765`

```bash
export CODELAB_PORT=4096
```

### CODELAB_HOST

Адрес привязки сервера.

| Значение | Описание |
|----------|----------|
| `127.0.0.1` | Только локальные подключения |
| `0.0.0.0` | Все сетевые интерфейсы |

**По умолчанию:** `127.0.0.1`

```bash
# Доступ из сети
export CODELAB_HOST=0.0.0.0
```

### CODELAB_HOME

Путь к домашней директории приложения.

**По умолчанию:** `~/.codelab`

```bash
export CODELAB_HOME=/opt/codelab/data
```

## Логирование

### CODELAB_LOG_LEVEL

Уровень детализации логов.

| Значение | Описание |
|----------|----------|
| `DEBUG` | Все сообщения, включая отладочные |
| `INFO` | Информационные сообщения и выше |
| `WARNING` | Предупреждения и ошибки |
| `ERROR` | Только ошибки |

**По умолчанию:** `INFO`

```bash
export CODELAB_LOG_LEVEL=DEBUG
```

## Сводная таблица

| Переменная | По умолчанию | Обязательная |
|------------|--------------|--------------|
| `CODELAB_LLM_PROVIDER` | `mock` | Нет |
| `CODELAB_LLM_API_KEY` | - | Да* |
| `CODELAB_LLM_BASE_URL` | - | Нет |
| `CODELAB_LLM_MODEL` | `gpt-4o` | Нет |
| `CODELAB_LLM_TEMPERATURE` | `0.7` | Нет |
| `CODELAB_LLM_MAX_TOKENS` | `8192` | Нет |
| `CODELAB_PORT` | `8765` | Нет |
| `CODELAB_HOST` | `127.0.0.1` | Нет |
| `CODELAB_HOME` | `~/.codelab` | Нет |
| `CODELAB_LOG_LEVEL` | `INFO` | Нет |

\* Обязательна для провайдеров `openai` и `anthropic`

## Пример .env файла

```env
# CodeLab Configuration
# =====================

# LLM провайдер
CODELAB_LLM_PROVIDER=openai
CODELAB_LLM_API_KEY=sk-your-api-key-here
CODELAB_LLM_MODEL=gpt-4o
CODELAB_LLM_TEMPERATURE=0.7
CODELAB_LLM_MAX_TOKENS=8192

# Сервер
CODELAB_PORT=8765
CODELAB_HOST=127.0.0.1

# Логирование
CODELAB_LOG_LEVEL=INFO
```

## См. также

- [Конфигурация](configuration.md) — общий справочник конфигурации
- [CLI команды](cli.md) — параметры командной строки
