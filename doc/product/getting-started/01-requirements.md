# Системные требования

> Минимальные и рекомендуемые требования для работы с CodeLab.

## Операционная система

| ОС | Поддержка | Примечания |
|----|-----------|------------|
| macOS 12+ | ✅ Полная | Рекомендуется |
| Linux (Ubuntu 22.04+) | ✅ Полная | Рекомендуется |
| Windows 10/11 | ⚠️ Частичная | Через WSL2 |

## Python

**Минимальная версия:** Python 3.12+

Проверка версии:
```bash
python3 --version
# Python 3.12.x
```

### Установка Python

**macOS (Homebrew):**
```bash
brew install python@3.12
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv
```

## uv (менеджер пакетов)

CodeLab использует [uv](https://docs.astral.sh/uv/) для управления зависимостями и виртуальными окружениями.

**Минимальная версия:** uv 0.4+

### Установка uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Или через Homebrew (macOS)
brew install uv

# Или через pip
pip install uv
```

Проверка установки:
```bash
uv --version
# uv 0.4.x
```

## Git

Для клонирования репозитория требуется Git.

```bash
git --version
# git version 2.x.x
```

## Сетевые требования

### Для работы с LLM

- Доступ к API OpenAI (`api.openai.com`) или другому LLM-провайдеру
- Валидный API-ключ

### Для Web UI

- Свободный порт (по умолчанию 8765)
- Современный браузер (Chrome, Firefox, Safari)

## Аппаратные требования

### Минимальные

- **RAM:** 2 GB
- **Диск:** 500 MB свободного места
- **CPU:** любой современный процессор

### Рекомендуемые

- **RAM:** 4+ GB
- **Диск:** 1+ GB свободного места
- **CPU:** многоядерный процессор

## API ключи

Для работы с реальными LLM требуется API-ключ:

| Провайдер | Переменная окружения | Получение |
|-----------|---------------------|-----------|
| OpenAI | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) |
| Anthropic | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) |
| OpenRouter | `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) |
| Zen | `ZEN_API_KEY` | [zen.opencode.ai](https://zen.opencode.ai) |
| Go | `GO_API_KEY` | [go.opencode.ai](https://go.opencode.ai) |
| Ollama | — | Локальный сервер, не требует ключа |
| LMStudio | — | Локальный сервер, не требует ключа |

> **Примечание:** Для тестирования можно использовать mock-провайдер без API-ключа.

## Проверка готовности

Выполните следующие команды для проверки:

```bash
# Python версия
python3 --version

# uv установлен
uv --version

# Git установлен
git --version

# Сеть работает (опционально)
curl -I https://api.openai.com
```

Если все команды выполнены успешно, вы готовы к [установке](02-installation.md).

## Решение проблем

### Python не найден

```bash
# macOS: используйте python3
alias python=python3

# Или укажите полный путь
/usr/local/bin/python3 --version
```

### uv не найден после установки

Добавьте путь в PATH:
```bash
export PATH="$HOME/.cargo/bin:$PATH"
```

Добавьте эту строку в `~/.zshrc` или `~/.bashrc` для постоянного эффекта.

## См. также

- [Установка](02-installation.md) — пошаговая инструкция установки
- [Быстрый старт](03-quickstart.md) — первый запуск
