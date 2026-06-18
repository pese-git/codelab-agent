# Интеграция с JetBrains IntelliJ IDEA

> Настройка CodeLab как AI агента в JetBrains IDE через ACP протокол и stdio транспорт.

## Обзор

JetBrains AI Assistant поддерживает подключение внешних AI агентов через ACP (Agent Client Protocol). CodeLab работает как agent server, обмениваясь JSON-RPC сообщениями через stdin/stdout.

Архитектура взаимодействия:

```
┌─────────────┐     stdin/stdout (JSON-RPC)     ┌──────────────┐
│  JetBrains  │ ◄─────────────────────────────► │   CodeLab    │
│ AI Assistant│                                 │ (ACP Server) │
└─────────────┘                                 └──────┬───────┘
                                                       │
                                              ┌────────▼────────┐
                                              │   LLM Provider   │
                                              │ (OpenAI, etc.)   │
                                              └─────────────────┘
```

Модель выбирается через dropdown в чате AI Assistant. JetBrains управляет MCP серверами нативно.

## Установка

### Вариант 1: Глобальная установка (рекомендуется для IDE)

Для использования в JetBrains IDE удобнее установить CodeLab глобально:

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

Для использования в JetBrains из локальной копии укажите полный путь к исполняемому файлу в конфигурации.

## Настройка JetBrains

### Способ 1: Через UI (Add custom Agent)

1. Откройте `Settings/Preferences` → `Tools` → `AI Assistant`
2. Найдите секцию **Agent Servers**
3. Нажмите **Add custom Agent (beta)**
4. Заполните поля:
   - **Name**: `Codelab Agent`
   - **Command**: полный путь к исполняемому файлу (например, `/Users/<username>/.local/bin/codelab`)
   - **Arguments**: `serve --stdio`
   - **Environment variables**: добавьте `CODELAB_LOG_LEVEL=DEBUG` при необходимости

### Способ 2: Через конфигурационный файл

Откройте или создайте файл `~/.jetbrains/acp.json`:

```json
{
  "agent_servers": {
    "Codelab Agent": {
      "command": "/Users/<username>/.local/bin/codelab",
      "args": ["serve", "--stdio"],
      "env": {
        "CODELAB_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

Замените `<username>` на ваше имя пользователя.

### API ключи

API ключи берутся из **системного окружения**, а не из `env` секции конфигурации. Установите их в shell-профиле (`~/.zshrc`, `~/.bashrc`):

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENROUTER_API_KEY="sk-or-..."
```

> **Примечание:** JetBrains наследует переменные окружения из родительского процесса. Убедитесь, что API ключи доступны в окружении, из которого запускается IDE.

## Конфигурация агента

### Основные параметры

| Параметр | Описание | Пример |
|----------|----------|--------|
| `command` | Путь к исполняемому файлу CodeLab | `/Users/<username>/.local/bin/codelab` |
| `args` | Аргументы командной строки | `["serve", "--stdio"]` |
| `env` | Переменные окружения процесса | `{"CODELAB_LOG_LEVEL": "DEBUG"}` |

### Дополнительные параметры

CodeLab поддерживает дополнительные параметры управления поведением агента. Их можно передать через `env`:

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

Модель выбирается через **dropdown в чате AI Assistant**. Формат модели: `provider/model`:

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
  "agent_servers": {
    "Codelab Agent": {
      "command": "/Users/<username>/.local/bin/codelab",
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
  "agent_servers": {
    "Codelab Agent": {
      "command": "/Users/<username>/.local/bin/codelab",
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
  "agent_servers": {
    "Codelab Agent": {
      "command": "/Users/<username>/.local/bin/codelab",
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

1. Откройте AI Assistant в JetBrains (`Cmd+Shift+A` → `AI Assistant`)
2. Выберите `Codelab Agent` из списка агентов
3. Выберите модель через dropdown в чате
4. Начните диалог с агентом

Агент имеет доступ к встроенным инструментам:
- **File System** — чтение и запись файлов
- **Terminal** — выполнение команд
- **Agent Plan** — планирование сложных задач

## MCP серверы

JetBrains AI Assistant нативно поддерживает MCP серверы — настраивайте их в конфигурации JetBrains, а не в CodeLab. CodeLab автоматически получит MCP инструменты через ACP протокол при создании сессии.

Подробнее о MCP: [MCP серверы](../extensions/mcp-servers.md).

## Troubleshooting

### Агент не появляется в списке

1. Проверьте установку:
   ```bash
   codelab --help
   ```
2. Проверьте, что путь в конфигурации указывает на существующий файл:
   ```bash
   ls -la /Users/<username>/.local/bin/codelab
   ```
3. Проверьте синтаксис `~/.jetbrains/acp.json`:
   ```bash
   python3 -c "import json; json.load(open('~/.jetbrains/acp.json'))"
   ```
4. Перезапустите IDE после изменения конфигурации

### Ошибка API ключа

```
AuthenticationError: API key is required
```

1. Убедитесь, что API ключ установлен в системном окружении
2. Проверьте, что IDE запущена из окружения с установленными переменными:
   ```bash
   # macOS: проверьте, что переменные доступны в GUI-окружении
   launchctl getenv OPENAI_API_KEY
   ```
3. Для macOS запустите IDE из терминала:
   ```bash
   open -a "IntelliJ IDEA"
   ```

### Модель не найдена

```
ModelNotFoundError: Model 'gpt-4o' not found for provider 'openai'
```

Используйте формат `provider/model`:

```bash
# В env конфигурации
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

1. Файл должен быть `~/.jetbrains/acp.json` (не `acp.json` в другом месте)
2. Перезапустите IDE после изменения файла
3. Проверьте логи IDE на ошибки парсинга конфигурации

## См. также

- [Настройка сервера](../server/server-setup.md) — режимы запуска сервера
- [Настройка LLM провайдеров](../llm/llm-providers.md) — подробная настройка провайдеров
- [MCP серверы](../extensions/mcp-servers.md) — подключение внешних инструментов
- [Справочник CLI](../../reference/cli.md) — все команды и опции
- [Переменные окружения](../../reference/environment.md) — полный список переменных
