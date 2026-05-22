# Справочник конфигурации

Полный справочник всех настроек CodeLab.

## Файлы конфигурации

CodeLab поддерживает два формата конфигурации:

### TOML файлы

| Файл | Приоритет | Описание | Коммитится |
|------|-----------|----------|------------|
| `~/.codelab/auth.toml` | Низший | Глобальные API keys | Нет |
| `codelab.toml` | Средний | Конфигурация проекта | Да |
| `codelab.local.toml` | Высокий | Локальные overrides | Нет |
| `--config <path>` | Высший | Кастомный файл | Зависит |

### Переменные окружения

| Файл | Приоритет | Описание |
|------|-----------|----------|
| Системные переменные | Высший | Переменные окружения ОС |
| `.env` (локальный) | Высокий | Настройки проекта |
| `~/.codelab/config/.env` | Низший | Глобальные настройки |

> **Примечание:** Переменные окружения переопределяют TOML значения.

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

### Полная конфигурация (.env)

```env
# LLM Configuration
CODELAB_LLM_PROVIDER=openai
CODELAB_LLM_API_KEY=sk-your-api-key-here
CODELAB_LLM_MODEL=openai/gpt-4o
CODELAB_LLM_TEMPERATURE=0.7
CODELAB_LLM_MAX_TOKENS=8192

# Server Configuration
CODELAB_PORT=8765
CODELAB_HOST=127.0.0.1
CODELAB_HOME=~/.codelab

# Logging
CODELAB_LOG_LEVEL=INFO
```

### TOML конфигурация (codelab.toml)

```toml
[llm]
provider = "openai"
model = "openai/gpt-4o"
temperature = 0.7
max_tokens = 8192

[llm.providers.openai]
api_key = "${OPENAI_API_KEY}"
base_url = "https://api.openai.com/v1"

[llm.providers.openai.models.gpt-4o]
context_window = 128000
max_output_tokens = 16384

[llm.fallback]
enabled = true
order = ["openai", "openrouter", "ollama"]
retry_on = ["rate_limit", "timeout"]
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

- [TOML конфигурация](../user-guide/13-toml-configuration.md) — полное руководство по TOML
- [Переменные окружения](03-environment.md) — детальное описание переменных
- [CLI команды](01-cli.md) — справочник командной строки
- [Настройка сервера](../user-guide/03-server-setup.md) — руководство по настройке
