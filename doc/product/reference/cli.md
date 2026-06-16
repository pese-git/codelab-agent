# Справочник CLI команд

CodeLab предоставляет единую точку входа `codelab` с несколькими режимами работы.

## Обзор команд

| Команда | Описание |
|---------|----------|
| `codelab` | Локальный режим: запускает сервер + TUI через stdio |
| `codelab serve` | Режим сервера: WebSocket API |
| `codelab serve --stdio` | Режим сервера: stdio транспорт для внешних клиентов |
| `codelab connect` | Режим клиента: подключение к серверу по WebSocket |
| `codelab connect --stdio` | Режим клиента: запуск агента как subprocess через stdio |

## Локальный режим (по умолчанию)

Запускает сервер как subprocess и TUI клиент через stdio транспорт:

```bash
codelab
```

Сервер запускается как изолированный subprocess, TUI подключается через stdio.
При закрытии TUI процесс сервера автоматически завершается.

### Глобальные опции

| Опция | Описание |
|-------|----------|
| `-v`, `--verbose` | Включить подробное логирование (DEBUG уровень) |

## codelab serve

Запускает WebSocket сервер для удалённых клиентов.

```bash
codelab serve [опции]
```

### Параметры

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--host` | `127.0.0.1` | Адрес для прослушивания |
| `--port` | `8765` | Порт для прослушивания |
| `--stdio` | — | Запустить stdio транспорт вместо WebSocket |
| `--require-auth` | — | Требовать `authenticate` перед `session/new` и `session/load` |
| `--auth-api-key` | — | API key для аутентификации (или env `ACP_SERVER_API_KEY`) |
| `--no-web` | — | Отключить Web UI на корневом пути `/` |
| `--log-level` | `INFO` | Уровень логирования: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--log-json` | — | JSON формат для логов (production) |
| `--log-file` | — | Путь к файлу логов. `default` для `~/.codelab/logs/codelab-server.log` |
| `--storage` | `memory` | Storage backend: `memory` или `json:/path/to/dir` |
| `--config` | — | Путь к custom TOML файлу конфигурации |
| `--trace-messages` | — | Детальное логирование всех JSON-RPC сообщений |

### Параметры LLM

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--llm-provider` | — | LLM провайдер (`openai`, `anthropic`, `openrouter`, `zen`, `go`, `ollama`, `lmstudio`, `mock`) |
| `--llm-model` | — | Модель LLM (формат `provider/model`) |
| `--llm-api-key` | — | API ключ для LLM провайдера |
| `--llm-base-url` | — | Base URL для LLM провайдера |
| `--llm-temperature` | — | Temperature для LLM (0.0-1.0) |
| `--llm-max-tokens` | — | Максимум токенов для LLM |
| `--system-prompt` | — | Системный промпт для агента |

### Параметры таймаутов LLM

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--llm-timeout-connect` | `30.0` | Таймаут подключения к LLM API (секунды) |
| `--llm-timeout-read` | `300.0` | Таймаут ожидания ответа от LLM API (секунды) |
| `--llm-timeout-write` | `30.0` | Таймаут отправки запроса к LLM API (секунды) |
| `--llm-timeout-pool` | `30.0` | Таймаут ожидания соединения из пула (секунды) |

### Параметры fallback

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--fallback-enabled` | — | Включить fallback цепочку при ошибках провайдера |
| `--fallback-strategy` | `sequential` | Стратегия fallback |
| `--fallback-order` | — | Порядок провайдеров через запятую (например, `openai,openrouter,ollama`) |

### Примеры

```bash
# Запуск на стандартном порту (WebSocket)
codelab serve

# Запуск на порту 4096 с доступом из сети
codelab serve --port 4096 --host 0.0.0.0

# Запуск только API без Web UI
codelab serve --no-web

# Запуск в stdio режиме (для IDE plugins)
codelab serve --stdio

# Запуск с подробным логированием
codelab -v serve --port 8080

# Запуск с JSON логами и файлом логов
codelab serve --log-level DEBUG --log-json --log-file default

# Запуск с персистентным хранилищем сессий
codelab serve --storage "json:~/.codelab/data/sessions"

# Запуск с аутентификацией
codelab serve --require-auth --auth-api-key "my-secret-key"

# Запуск с конкретным LLM провайдером
codelab serve --llm-provider openai --llm-model openai/gpt-4o --llm-api-key "$OPENAI_API_KEY"

# Запуск с fallback цепочкой
codelab serve --fallback-enabled --fallback-order openai,openrouter,ollama

# Запуск с трассировкой сообщений
codelab serve --trace-messages

# Запуск с custom TOML конфигурацией
codelab serve --config /path/to/custom.toml

# Запуск с кастомными таймаутами
codelab serve --llm-timeout-read 600 --llm-timeout-connect 60
```

### Endpoints

После запуска сервера доступны:

| Endpoint | Описание |
|----------|----------|
| `ws://{host}:{port}/acp/ws` | WebSocket API для ACP клиентов |
| `http://{host}:{port}/` | Web UI (если не отключён `--no-web`) |

В режиме `--stdio` endpoints не доступны — обмен через stdin/stdout.

## codelab connect

Запускает TUI клиент и подключается к серверу.

```bash
codelab connect [опции]
```

### Параметры

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `--host` | `127.0.0.1` | Адрес сервера |
| `--port` | `8765` | Порт сервера |
| `--cwd` | текущая директория | Рабочая директория проекта |
| `--stdio` | - | Запустить агент как subprocess через stdio |
| `--agent-command` | `codelab serve --stdio` | Команда для запуска агента (с --stdio) |

### Примеры

```bash
# Подключение к локальному серверу (WebSocket)
codelab connect

# Подключение к удалённому серверу
codelab connect --host server.example.com --port 4096

# Подключение с указанием рабочей директории
codelab connect --cwd ~/projects/myapp

# Запуск агента как subprocess (stdio транспорт)
codelab connect --stdio --cwd ~/projects/myapp

# Кастомная команда агента
codelab connect --stdio --agent-command "codelab serve --stdio" --cwd ~/projects/myapp
```

## Приоритет конфигурации

Параметры CLI имеют наивысший приоритет. Значения по умолчанию читаются из:

1. **Переменные окружения системы** (наивысший приоритет)
2. **`.env` в текущей директории** (локальный проект)
3. **`~/.codelab/config/.env`** (глобальные настройки)

## Домашняя директория

При первом запуске создаётся структура `~/.codelab/`:

```
~/.codelab/
├── config/       # Конфигурационные файлы (.env)
├── logs/         # Файлы логов (codelab.log)
├── data/
│   ├── sessions/ # Сохранённые сессии
│   ├── history/  # История чатов
│   ├── policies/ # Глобальные политики разрешений
│   └── observability/ # Observability данные (spans, metrics, events)
└── cache/        # Кэш MCP и временные данные
```

## Логирование

Логи записываются в `~/.codelab/logs/codelab.log` с автоматической ротацией.

Уровень логирования:
- По умолчанию: `INFO`
- С флагом `-v`: `DEBUG`
- Через переменную: `CODELAB_LOG_LEVEL`

## См. также

- [Переменные окружения](environment.md) — полный список переменных
- [Конфигурация](configuration.md) — справочник настроек
- [Быстрый старт](../getting-started/quickstart.md) — начало работы
