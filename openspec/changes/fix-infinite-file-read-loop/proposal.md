# Fix Infinite File Read Loop

## Проблема

Сессия уходит в вечный цикл чтения файлов:
- LLM генерирует tool calls для `fs/read_text_file`
- Каждый tool call выполняет чтение файла через RPC
- Нет кэширования между tool calls
- Нет информации о том, какие файлы уже прочитаны
- Нет лимитов на количество чтений

## Анализ логов

Из логов видно:
- `lib/main.dart` читается 5 раз
- `lib/weather_service.dart` читается 4 раза
- `lib/weather_model_simple.dart` читается 4 раза
- `analysis_options.yaml` читается 4 раза

Паттерн:
1. Во время `context.gather` - массовое чтение файлов
2. После LLM генерирует tool calls
3. Каждый tool call - `fs/read_text_file`
4. Файлы читаются повторно, даже если уже были в контексте

## Существующая инфраструктура

**КРИТИЧЕСКОЕ ОБНАРУЖЕНИЕ:** В проекте уже реализован Cache Manager (Фаза 2 Context Manager):

### 1. FileContentCache (`src/codelab/server/agent/context/file_cache.py`)
- `InMemoryFileCache` - LRU кэш с методами `get()`, `set()`, `invalidate()`
- `SessionFileCacheRegistry` - реестр кэшей для каждой сессии
- `InvalidationSignalBus` - шина сигналов для инвалидации

### 2. FileCacheDecorator (`src/codelab/server/agent/context/file_cache_decorator.py`)
- Оборачивает `FileSystemToolExecutor`
- Перехватывает `fs/read` и `fs/write`
- **Интегрирован в DI** через `PromptOrchestratorBuilder`

### 3. Конфигурация
- `agents.context.enabled = true` ✅
- `agents.context.file_cache = true` ✅

## КРИТИЧЕСКАЯ ОШИБКА в FileCacheDecorator

**Текущая логика (строки 64-105):**
```python
async def execute(self, session, arguments):
    result = await self._wrapped.execute(session, arguments)  # ← ВСЕГДА читает файл!
    
    if not result.success:
        return result
    
    # Только ПОСЛЕ чтения сохраняет в кэш
    if operation == "read":
        self._handle_read(path, result, cache)  # cache.set(path, content)
```

**Проблема:** Декоратор **не проверяет кэш перед чтением**! Он всегда вызывает `wrapped.execute()`, даже если файл уже в кэше.

## Решение

### 1. Исправить FileCacheDecorator (ПРИОРИТЕТ 1)
- Добавить проверку кэша **перед** вызовом `wrapped.execute()`
- Возвращать содержимое из кэша без RPC вызова
- Сохранять в кэш после успешного чтения

### 2. Добавить лимиты на чтения
- Максимум 3 чтения одного файла за сессию
- Максимум 20 чтений файлов за одну итерацию
- Превышение лимита - возвращать ошибку

### 3. Информирование LLM
- Добавлять в system prompt список уже прочитанных файлов
- LLM будет знать, какие файлы уже в контексте
- Снижать количество повторных запросов

### 4. Метрики кэша
- `file_cache_hits` - количество попаданий в кэш
- `file_cache_misses` - количество промахов
- `file_read_limit_exceeded` - превышение лимита

## Ожидаемый результат

- Снижение количества RPC вызовов в 3-5 раз
- Уменьшение времени выполнения tool calls
- Снижение нагрузки на файловую систему
- Предотвращение вечных циклов

## Оценка сложности

- Исправление FileCacheDecorator: 2 часа
- Добавление лимитов: 2 часа
- Информирование LLM: 1 час
- Метрики: 1 час

**Итого:** 6 часов (1 рабочий день)
