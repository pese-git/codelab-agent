# Интеграция с Visual Studio Code

> Настройка CodeLab как AI агента в VS Code через ACP протокол и stdio транспорт.

## Обзор

Visual Studio Code поддерживает подключение внешних AI агентов через ACP (Agent Client Protocol) с помощью плагина **ACP Client**. CodeLab работает как agent server, обмениваясь JSON-RPC сообщениями через stdin/stdout.

Архитектура взаимодействия:

```
┌─────────────┐     stdin/stdout (JSON-RPC)     ┌──────────────┐
│  VS Code    │ ◄─────────────────────────────► │   CodeLab    │
│ ACP Client  │                                 │ (ACP Server) │
└─────────────┘                                 └──────┬───────┘
                                                       │
                                              ┌────────▼────────┐
                                              │   LLM Provider   │
                                              │ (OpenAI, etc.)   │
                                              └─────────────────┘
```

Модель и дополнительные параметры (`mode`, `_agent`) выбираются через UI плагина (agent chat).

## Установка

### Вариант 1: Глобальная установка (рекомендуется для IDE)

Для использования в VS Code удобнее установить CodeLab глобально:

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

Убедитесь, что исполняемый файл доступен в PATH:

```bash
which codelab
# /Users/<username>/.local/bin/codelab
```

### Вариант 2: Установка из локальной копии

Если у вас уже есть локальная копия репозитория:

```bash
cd codelab-agent/codelab
uv sync --extra full

# Проверка
uv run codelab --help
```

Для использования в VS Code из локальной копии укажите полный путь к исполняемому файлу в конфигурации.

### Установка плагина ACP Client

Установите плагин **ACP Client** из VS Code Marketplace или через командную палитру:

1. `Cmd+Shift+X` (Extensions)
2. Поиск: `ACP Client`
3. Install

## Настройка VS Code

### 1. Откройте настройки

`Cmd+,` (macOS) или `Ctrl+,` (Windows/Linux) → откройте `settings.json`

Или через командную палитру: `Cmd+Shift+P` → `Preferences: Open Settings (JSON)`

### 2. Добавьте конфигурацию агента

В `settings.json` добавьте секцию `acp.agents`:

```json
{
  "acp.agents": {
    "CodeLab": {
      "command": "codelab",
      "args": [
        "serve",
        "--stdio"
      ],
      "env": {
        "CODELAB_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

Для локальной установки укажите полный путь:

```json
{
  "acp.agents": {
    "CodeLab": {
      "command": "/Users/<username>/Projects/codelab-agent/codelab/.venv/bin/codelab",
      "args": [
        "serve",
        "--stdio"
      ],
      "env": {
        "CODELAB_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

### 3. Настройте API ключи

API ключи берутся из **системного окружения**, а не из `env` секции конфигурации. Установите их в shell-профиле (`~/.zshrc`, `~/.bashrc`):

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENROUTER_API_KEY="sk-or-..."
```

> **Примечание:** VS Code наследует переменные окружения из родительского процесса. Убедитесь, что API ключи доступны в окружении, из которого запускается IDE.

## Конфигурация агента

### Основные параметры

| Параметр | Описание | Пример |
|----------|----------|--------|
| `command` | Команда запуска CodeLab | `codelab` или полный путь |
| `args` | Аргументы командной строки | `["serve", "--stdio"]` |
| `env` | Переменные окружения процесса | `{"CODELAB_LOG_LEVEL": "DEBUG"}` |

### Дополнительные параметры

Модель и параметры агента (`mode`, `_agent`) выбираются через **UI плагина** (agent chat dropdown).

Переменные окружения для процесса CodeLab:

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `CODELAB_LLM_PROVIDER` | Провайдер LLM (если не выбран в UI) | `mock` |
| `CODELAB_LLM_MODEL` | Модель в формате `provider/model` | `mock/mock-model` |
| `CODELAB_LLM_API_KEY` | Универсальный API ключ | — |
| `CODELAB_LLM_BASE_URL` | Base URL для совместимых API | — |
| `CODELAB_LLM_TEMPERATURE` | Temperature (0.0–1.0) | `0.7` |
| `CODELAB_LLM_MAX_TOKENS` | Максимум токенов ответа | `8192` |
| `CODELAB_LOG_LEVEL` | Уровень логирования | `INFO` |
| `CODELAB_HOME` | Домашняя директория | `~/.codelab` |

## Поддерживаемые LLM провайдеры

Модель выбирается через **dropdown в UI плагина**. Формат модели: `provider/model`:

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

**Базовая (модель через UI):**

```json
{
  "acp.agents": {
    "CodeLab": {
      "command": "codelab",
      "args": ["serve", "--stdio"],
      "env": {
        "CODELAB_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

**С фиксированным провайдером (модель через env):**

```json
{
  "acp.agents": {
    "CodeLab": {
      "command": "codelab",
      "args": ["serve", "--stdio"],
      "env": {
        "CODELAB_LLM_PROVIDER": "openai",
        "CODELAB_LLM_MODEL": "openai/gpt-4o",
        "CODELAB_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

**Ollama (локальная модель):**

```json
{
  "acp.agents": {
    "CodeLab": {
      "command": "codelab",
      "args": ["serve", "--stdio"],
      "env": {
        "CODELAB_LLM_PROVIDER": "ollama",
        "CODELAB_LLM_MODEL": "ollama/llama3.1:70b",
        "CODELAB_LLM_BASE_URL": "http://localhost:11434/v1"
      }
    }
  }
}
```

## Использование

После настройки:

1. Откройте ACP Client в VS Code (иконка в Activity Bar или `Cmd+Shift+P` → `ACP Client: Open`)
2. Выберите `CodeLab` из списка агентов
3. Выберите модель через dropdown в чате
4. Начните диалог с агентом

Агент имеет доступ к встроенным инструментам:
- **File System** — чтение и запись файлов
- **Terminal** — выполнение команд
- **Agent Plan** — планирование сложных задач

## MCP серверы

> **Ограничение:** На данный момент MCP серверы **не поддерживаются** при использовании VS Code + CodeLab через stdio transport.

Для подключения MCP серверов используйте `codelab.toml` в корне проекта (настройка на стороне CodeLab):

```toml
# codelab.toml в корне вашего проекта

[[mcp.servers]]
name = "filesystem"
type = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/project"]
```

Поддержка MCP через ACP Client для VS Code находится в разработке.

Подробнее о MCP: [MCP серверы](14-mcp-servers.md).

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
5. Перезапустите VS Code после изменения конфигурации

### Ошибка API ключа

```
AuthenticationError: API key is required
```

1. Убедитесь, что API ключ установлен в системном окружении
2. Проверьте, что VS Code запущен из окружения с установленными переменными:
   ```bash
   # macOS: проверьте, что переменные доступны в GUI-окружении
   launchctl getenv OPENAI_API_KEY
   ```
3. Для macOS запустите VS Code из терминала:
   ```bash
   code .
   ```

### Модель не найдена

```
ModelNotFoundError: Model 'gpt-4o' not found for provider 'openai'
```

Используйте формат `provider/model`:

```bash
# В env конфигурации или при выборе в UI
"CODELAB_LLM_MODEL": "openai/gpt-4o"
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
3. Убедитесь, что `CODELAB_LLM_PROVIDER` установлен (по умолчанию `mock`)

### Агент зависает или не отвечает

1. Установите `CODELAB_LOG_LEVEL: "DEBUG"` в `env` секции
2. Проверьте логи в `~/.codelab/logs/codelab.log`
3. Убедитесь, что LLM провайдер доступен (нет rate limit, API ключ валиден)

### Конфигурация не применяется

1. Ключ должен быть `acp.agents` (не `acp.agentServers`)
2. Перезапустите VS Code после изменения `settings.json`
3. Проверьте Output панель на ошибки ACP Client

## См. также

- [Настройка сервера](03-server-setup.md) — режимы запуска сервера
- [Настройка LLM провайдеров](11-llm-providers.md) — подробная настройка провайдеров
- [MCP серверы](14-mcp-servers.md) — подключение внешних инструментов
- [Справочник CLI](../reference/01-cli.md) — все команды и опции
- [Переменные окружения](../reference/03-environment.md) — полный список переменных
