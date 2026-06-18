# Интеграция с Zed IDE

> Настройка CodeLab как AI агента в Zed IDE через ACP протокол и stdio транспорт.

## Обзор

Zed IDE поддерживает подключение внешних AI агентов через ACP (Agent Client Protocol). CodeLab работает как agent server, обмениваясь JSON-RPC сообщениями через stdin/stdout.

Архитектура взаимодействия:

```
┌─────────────┐     stdin/stdout (JSON-RPC)     ┌──────────────┐
│   Zed IDE   │ ◄─────────────────────────────► │   CodeLab    │
│  (ACP Client)│                                 │ (ACP Server) │
└─────────────┘                                 └──────┬───────┘
                                                       │
                                              ┌────────▼────────┐
                                              │   LLM Provider   │
                                              │ (OpenAI, etc.)   │
                                              └─────────────────┘
```

Zed передаёт модель и параметры агента через `default_config_options`, а CodeLab использует системные переменные окружения для API ключей.

## Установка

### Вариант 1: Глобальная установка (рекомендуется для IDE)

Для использования в Zed IDE удобнее установить CodeLab глобально:

```bash
# Через pipx (изолированная установка)
pipx install "git+https://github.com/pese-git/codelab-agent.git@main#subdirectory=codelab"

# Или через pip
pip install "git+https://github.com/pese-git/codelab-agent.git@main#subdirectory=codelab"
```

Проверка установки:

```bash
codelab --help
```

### Вариант 2: Установка из локальной копии

Если у вас уже есть локальная копия репозитория:

```bash
cd codelab-agent/codelab
uv sync --extra full

# Проверка
uv run codelab --help
```

Для использования в Zed из локальной копии укажите полный путь к исполняемому файлу в конфигурации.

## Настройка Zed IDE

### 1. Откройте настройки Zed

`Zed → Settings → Open Settings` (или `Cmd+,` / `Ctrl+,`)

### 2. Добавьте конфигурацию агента

В `settings.json` добавьте секцию `agent_servers`:

```json
{
  "agent_servers": {
    "Codelab Agent": {
      "type": "custom",
      "command": "codelab",
      "args": ["serve", "--stdio"],
      "env": {
        "CODELAB_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

### 3. Настройте API ключи

API ключи берутся из **системного окружения**, а не из `env` секции Zed. Установите их в shell-профиле (`~/.zshrc`, `~/.bashrc`) или через `.env` файл:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENROUTER_API_KEY="sk-or-..."
```

> **Примечание:** Zed наследует переменные окружения из родительского процесса. Убедитесь, что API ключи доступны в окружении, из которого запускается Zed.

## Конфигурация агента

### default_config_options

Параметры, которые Zed передаёт CodeLab при создании сессии:

| Параметр | Описание | Пример |
|----------|----------|--------|
| `model` | Модель LLM в формате `provider/model` | `openrouter/qwen3.6-plus` |
| `mode` | Режим работы агента | `bypass`, `standard` |
| `_agent` | Имя агента | `universal` |

### favorite_config_option_values

Фиксирует допустимые значения для опций, которые Zed показывает в UI для переключения:

```json
"favorite_config_option_values": {
  "mode": ["standard", "bypass"]
}
```

### env

Переменные окружения, специфичные для процесса CodeLab. Обычно здесь указывают только служебные параметры:

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `CODELAB_LOG_LEVEL` | Уровень логирования | `INFO` |
| `CODELAB_HOME` | Домашняя директория | `~/.codelab` |

API ключи и модель **не** указываются здесь — используйте системное окружение и `default_config_options.model`.

## Поддерживаемые LLM провайдеры

Модель задаётся в `default_config_options.model` в формате `provider/model`:

| Провайдер | Формат модели | Переменная API ключа |
|-----------|---------------|----------------------|
| OpenAI | `openai/gpt-4o` | `OPENAI_API_KEY` |
| Anthropic | `anthropic/claude-sonnet-4` | `ANTHROPIC_API_KEY` |
| OpenRouter | `openrouter/qwen3.6-plus` | `OPENROUTER_API_KEY` |
| Zen | `zen/zen-sonnet` | `ZEN_API_KEY` |
| Go | `go/go-fast` | `GO_API_KEY` |
| Ollama | `ollama/llama3.1:70b` | не требуется |
| LMStudio | `lmstudio/local-model` | не требуется |
| Mock | `mock/mock-model` | не требуется |

### Примеры конфигураций

**OpenRouter:**

```json
{
  "agent_servers": {
    "Codelab Agent": {
      "type": "custom",
      "command": "codelab",
      "args": ["serve", "--stdio"],
      "default_config_options": {
        "mode": "bypass",
        "_agent": "universal",
        "model": "openrouter/qwen3.6-plus"
      }
    }
  }
}
```

**OpenAI:**

```json
{
  "agent_servers": {
    "Codelab Agent": {
      "type": "custom",
      "command": "codelab",
      "args": ["serve", "--stdio"],
      "default_config_options": {
        "mode": "bypass",
        "_agent": "universal",
        "model": "openai/gpt-4o"
      }
    }
  }
}
```

**Anthropic:**

```json
{
  "agent_servers": {
    "Codelab Agent": {
      "type": "custom",
      "command": "codelab",
      "args": ["serve", "--stdio"],
      "default_config_options": {
        "mode": "bypass",
        "_agent": "universal",
        "model": "anthropic/claude-sonnet-4"
      }
    }
  }
}
```

**Ollama (локальная модель):**

```json
{
  "agent_servers": {
    "Codelab Agent": {
      "type": "custom",
      "command": "codelab",
      "args": ["serve", "--stdio"],
      "default_config_options": {
        "mode": "bypass",
        "_agent": "universal",
        "model": "ollama/llama3.1:70b"
      },
      "env": {
        "CODELAB_LLM_BASE_URL": "http://localhost:11434/v1"
      }
    }
  }
}
```

## Использование

После настройки:

1. Откройте AI панель в Zed (`Cmd+Shift+P` → `Zed AI: Toggle`)
2. Выберите `Codelab Agent` из списка агентов
3. Начните диалог с агентом

Агент имеет доступ к встроенным инструментам:
- **File System** — чтение и запись файлов
- **Terminal** — выполнение команд
- **Agent Plan** — планирование сложных задач

## MCP серверы

Zed IDE нативно поддерживает MCP серверы — настраивайте их в конфигурации Zed, а не в CodeLab. CodeLab автоматически получит MCP инструменты через ACP протокол при создании сессии.

Подробнее о MCP: [MCP серверы](../extensions/mcp-servers.md).

## Troubleshooting

### Агент не появляется в списке

1. Проверьте установку:
   ```bash
   codelab --help
   ```
2. Убедитесь, что `settings.json` содержит валидный JSON
3. Проверьте, что `command` указывает на существующий исполняемый файл:
   ```bash
   which codelab
   ```
4. Для локальной установки укажите полный путь:
   ```json
   {
     "command": "/path/to/codelab-agent/codelab/.venv/bin/codelab"
   }
   ```

### Ошибка API ключа

```
AuthenticationError: API key is required
```

1. Убедитесь, что API ключ установлен в системном окружении
2. Проверьте, что Zed запущен из окружения с установленными переменными:
   ```bash
   # macOS: проверьте, что переменные доступны в GUI-окружении
   launchctl getenv OPENAI_API_KEY
   ```
3. Для macOS добавьте переменные в `~/.zshrc` и перезапустите Zed из терминала:
   ```bash
   open -a Zed
   ```

### Модель не найдена

```
ModelNotFoundError: Model 'gpt-4o' not found for provider 'openai'
```

Используйте формат `provider/model` в `default_config_options.model`:

```json
"model": "openai/gpt-4o"
```

Не просто `gpt-4o`.

### Ошибка запуска stdio транспорта

```
Error: stdio transport failed
```

1. Проверьте логи:
   ```bash
   cat ~/.codelab/logs/codelab.log | tail -50
   ```
2. Запустите вручную для проверки:
   ```bash
   codelab serve --stdio
   ```
3. Включите `DEBUG` логирование в `env` секции

### Агент зависает или не отвечает

1. Установите `CODELAB_LOG_LEVEL: "DEBUG"` в `env` секции
2. Проверьте логи в `~/.codelab/logs/codelab.log`
3. Убедитесь, что LLM провайдер доступен (нет rate limit, API ключ валиден)

### Порт занят (при использовании WebSocket)

Если вы используете `codelab serve` без `--stdio`:

```bash
# Найти процесс на порту
lsof -i :8765

# Использовать другой порт
codelab serve --port 9000
```

Для Zed IDE всегда используйте `--stdio` — порт не требуется.

## См. также

- [Настройка сервера](../server/server-setup.md) — режимы запуска сервера
- [Настройка LLM провайдеров](../llm/llm-providers.md) — подробная настройка провайдеров
- [MCP серверы](../extensions/mcp-servers.md) — подключение внешних инструментов
- [Справочник CLI](../../reference/cli.md) — все команды и опции
- [Переменные окружения](../../reference/environment.md) — полный список переменных
