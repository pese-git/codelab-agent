# Справочник конфигурации

Полный справочник всех настроек CodeLab.

## Файлы конфигурации

CodeLab использует `.env` файлы для конфигурации:

| Файл | Приоритет | Описание |
|------|-----------|----------|
| Системные переменные | Высший | Переменные окружения ОС |
| `.env` (локальный) | Средний | Настройки проекта |
| `~/.codelab/config/.env` | Низший | Глобальные настройки |

## Конфигурация LLM

### Провайдер

| Опция | Значения | По умолчанию | Описание |
|-------|----------|--------------|----------|
| `CODELAB_LLM_PROVIDER` | `openai`, `anthropic`, `openrouter`, `zen`, `go`, `ollama`, `lmstudio`, `mock` | `mock` | Тип LLM провайдера |
| `CODELAB_LLM_MODEL` | `provider/model` | `mock/mock-model` | Модель в формате `"provider/model"` |

### Аутентификация

| Опция | Описание |
|-------|----------|
| `OPENAI_API_KEY` | API ключ OpenAI |
| `ANTHROPIC_API_KEY` | API ключ Anthropic |
| `OPENROUTER_API_KEY` | API ключ OpenRouter |
| `ZEN_API_KEY` | API ключ Zen |
| `GO_API_KEY` | API ключ Go |
| `CODELAB_LLM_BASE_URL` | Кастомный URL API (для совместимых сервисов) |

### Параметры модели

| Опция | По умолчанию | Описание |
|-------|--------------|----------|
| `CODELAB_LLM_MODEL` | `mock/mock-model` | Модель LLM в формате `"provider/model"` |
| `CODELAB_LLM_TEMPERATURE` | `0.7` | Temperature (0.0-1.0) |
| `CODELAB_LLM_MAX_TOKENS` | `8192` | Максимум токенов ответа |

### Fallback

| Опция | Значения | По умолчанию | Описание |
|-------|----------|--------------|----------|
| `CODELAB_FALLBACK_ENABLED` | `true`, `false` | `false` | Включить fallback цепочку |
| `CODELAB_FALLBACK_STRATEGY` | `sequential` | `sequential` | Стратегия fallback |
| `CODELAB_FALLBACK_ORDER` | `openai,openrouter,ollama` | — | Порядок провайдеров |

## Конфигурация сервера

| Опция | По умолчанию | Описание |
|-------|--------------|----------|
| `CODELAB_PORT` | `8765` | Порт WebSocket сервера |
| `CODELAB_HOST` | `127.0.0.1` | Адрес привязки сервера |
| `CODELAB_HOME` | `~/.codelab` | Домашняя директория приложения |

## Конфигурация логирования

| Опция | Значения | По умолчанию | Описание |
|-------|----------|--------------|----------|
| `CODELAB_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` | Уровень логирования |

## Пример конфигурации

### Минимальная конфигурация для работы с OpenAI

```env
CODELAB_LLM_PROVIDER=openai
CODELAB_LLM_API_KEY=sk-your-api-key-here
```

### Полная конфигурация

```env
# LLM Configuration
CODELAB_LLM_PROVIDER=openai
CODELAB_LLM_API_KEY=sk-your-api-key-here
CODELAB_LLM_MODEL=gpt-4o
CODELAB_LLM_TEMPERATURE=0.7
CODELAB_LLM_MAX_TOKENS=8192

# Server Configuration
CODELAB_PORT=8765
CODELAB_HOST=127.0.0.1
CODELAB_HOME=~/.codelab

# Logging
CODELAB_LOG_LEVEL=INFO
```

### Использование совместимого API (OpenRouter, Azure)

```env
CODELAB_LLM_PROVIDER=openai
CODELAB_LLM_API_KEY=your-openrouter-key
CODELAB_LLM_BASE_URL=https://openrouter.ai/api/v1
CODELAB_LLM_MODEL=anthropic/claude-3-opus
```

## Конфигурация сессий

Настройки сессий задаются через ACP протокол при создании сессии (`session/new`):

| Параметр | Тип | Описание |
|----------|-----|----------|
| `workingDirectory` | `string` | Рабочая директория проекта |
| `environmentVariables` | `object` | Переменные окружения для инструментов |
| `mcpServers` | `array` | Список MCP серверов для подключения |

### Пример конфигурации сессии

```json
{
  "workingDirectory": "/home/user/project",
  "environmentVariables": {
    "NODE_ENV": "development"
  },
  "mcpServers": [
    {
      "name": "filesystem",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
    }
  ]
}
```

## Структура домашней директории

```
~/.codelab/
├── config/
│   └── .env              # Глобальная конфигурация
├── logs/
│   └── codelab.log       # Логи с ротацией
├── data/
│   ├── sessions/         # JSON файлы сессий
│   ├── history/          # История чатов клиента
│   └── policies/         # Глобальные политики разрешений
└── cache/                # Временные данные и кэш MCP
```

## См. также

- [Переменные окружения](03-environment.md) — детальное описание переменных
- [CLI команды](01-cli.md) — справочник командной строки
- [Настройка сервера](../user-guide/03-server-setup.md) — руководство по настройке
