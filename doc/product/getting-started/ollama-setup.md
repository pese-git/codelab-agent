# Настройка Ollama для CodeLab

Ollama позволяет запускать LLM модели локально. CodeLab поддерживает Ollama через OpenAI-совместимый API.

## Установка Ollama

### macOS (Homebrew)

```bash
brew install ollama
```

### macOS / Linux (скрипт установки)

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Windows

Скачайте установщик с [ollama.com/download](https://ollama.com/download) и запустите его.

### Проверка установки

```bash
ollama --version
```

## Запуск Ollama

Ollama работает как фоновый сервис. Запустите его:

```bash
ollama serve
```

По умолчанию сервер запускается на `http://localhost:11434`.

> **Примечание:** На macOS при установке через Homebrew или установщик Ollama может запускаться автоматически.

## Скачивание модели gemma4

Загрузите модель Gemma 4:

```bash
ollama pull gemma4
```

Для систем с ограниченной памятью можно использовать меньшую версию:

```bash
ollama pull gemma4:12b
```

### Другие рекомендуемые модели

| Модель | Команда | Описание |
|--------|---------|----------|
| Llama 3.3 | `ollama pull llama3.3` | Meta Llama 3.3 70B |
| Qwen 3 | `ollama pull qwen3` | Alibaba Qwen 3 |
| DeepSeek R1 | `ollama pull deepseek-r1` | DeepSeek R1 с reasoning |

Полный список моделей: [ollama.com/library](https://ollama.com/library)

## Проверка работы

### Проверка сервера

```bash
curl http://localhost:11434/api/version
```

### Проверка модели

```bash
ollama run gemma4 "Привет! Ответь одним предложением."
```

### Проверка OpenAI-совместимого API

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4",
    "messages": [{"role": "user", "content": "Привет!"}]
  }'
```

## Подключение к CodeLab

### Настройка переменных окружения

Создайте или отредактируйте файл `.env` в директории `codelab/`:

```bash
# LLM Provider - используем openai для совместимости
CODELAB_LLM_PROVIDER=openai

# API Key - Ollama не требует ключ, но поле обязательно
CODELAB_LLM_API_KEY=ollama

# Base URL - указываем на Ollama
CODELAB_LLM_BASE_URL=http://localhost:11434/v1

# Model - имя модели в Ollama
CODELAB_LLM_MODEL=gemma4

# Temperature (опционально)
CODELAB_LLM_TEMPERATURE=0.7
```

### Запуск CodeLab с Ollama

1. Убедитесь, что Ollama запущен:
   ```bash
   ollama serve
   ```

2. Запустите CodeLab сервер:
   ```bash
   cd codelab
   uv run codelab serve
   ```

3. Подключитесь клиентом:
   ```bash
   cd codelab
   uv run codelab connect
   ```

## Устранение неполадок

### Ollama не отвечает

Проверьте, запущен ли сервис:
```bash
ps aux | grep ollama
```

Перезапустите:
```bash
ollama serve
```

### Модель не найдена

Убедитесь, что модель загружена:
```bash
ollama list
```

### Нехватка памяти

Используйте модели меньшего размера или с квантизацией:
```bash
ollama pull gemma4:12b
# или
ollama pull llama3.2:3b
```

### Порт занят

Запустите Ollama на другом порту:
```bash
OLLAMA_HOST=127.0.0.1:11435 ollama serve
```

И обновите `CODELAB_LLM_BASE_URL`:
```bash
CODELAB_LLM_BASE_URL=http://localhost:11435/v1
```

## Дополнительные ресурсы

- [Документация Ollama](https://github.com/ollama/ollama/blob/main/docs/README.md)
- [Список моделей](https://ollama.com/library)
- [OpenAI Compatibility](https://github.com/ollama/ollama/blob/main/docs/openai.md)
