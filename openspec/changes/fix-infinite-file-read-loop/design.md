# Design: Fix Infinite File Read Loop

## Архитектура

### 1. Исправление FileCacheDecorator (ПРИОРИТЕТ 1)

**Где:** `src/codelab/server/agent/context/file_cache_decorator.py`

**Что:** Добавить проверку кэша **перед** вызовом `wrapped.execute()`

**Текущая логика:**
```python
async def execute(self, session, arguments):
    result = await self._wrapped.execute(session, arguments)  # ← ВСЕГДА читает
    
    if not result.success:
        return result
    
    if operation == "read":
        self._handle_read(path, result, cache)  # ← Только сохраняет
```

**Исправленная логика:**
```python
async def execute(self, session, arguments):
    operation = arguments.get("operation", "")
    path = arguments.get("path", "")
    
    # ПРОВЕРИТЬ КЭШ ПЕРЕД ЧТЕНИЕМ
    if operation == "read" and path:
        cache = self._get_cache_for_session(session)
        if cache is not None:
            cached_content = cache.get(path)
            if cached_content is not None:
                logger.debug("file_cache_hit", path=path)
                return ToolExecutionResult(
                    success=True,
                    output=cached_content,
                    metadata={"from_cache": True}
                )
    
    # Если не в кэше - выполнить wrapped.execute()
    result = await self._wrapped.execute(session, arguments)
    
    if not result.success:
        return result
    
    # Сохранить в кэш после успешного чтения
    if operation == "read" and path:
        cache = self._get_cache_for_session(session)
        if cache is not None:
            cache.set(path, result.output)
            logger.debug("file_cache_set", path=path)
    
    return result
```

**Зачем:**
- Избегать повторных RPC вызовов
- Ускорить выполнение tool calls
- Снижить нагрузку на файловую систему

### 2. Добавить лимиты на чтения

**Где:** `src/codelab/server/agent/context/file_cache_decorator.py`

**Что:** Добавить подсчёт чтений и проверку лимитов

**Логика:**
```python
class FileCacheDecorator(ToolExecutorDecorator):
    def __init__(self, ...):
        self._read_counts: dict[str, dict[str, int]] = {}  # session_id -> {path -> count}
        self._max_reads_per_file = 3
        self._max_reads_per_iteration = 20
    
    async def execute(self, session, arguments):
        operation = arguments.get("operation", "")
        path = arguments.get("path", "")
        
        if operation == "read" and path:
            # Проверить лимит файла
            session_counts = self._read_counts.get(session.session_id, {})
            file_count = session_counts.get(path, 0)
            
            if file_count >= self._max_reads_per_file:
                logger.warning(
                    "file_read_limit_exceeded",
                    path=path,
                    count=file_count,
                    max=self._max_reads_per_file
                )
                return ToolExecutionResult(
                    success=False,
                    output=None,
                    error=f"File {path} read limit exceeded (max {self._max_reads_per_file})"
                )
            
            # Увеличить счётчик
            if session.session_id not in self._read_counts:
                self._read_counts[session.session_id] = {}
            self._read_counts[session.session_id][path] = file_count + 1
```

**Зачем:**
- Предотвратить вечные циклы
- Контролировать ресурсы
- Улучшить стабильность

### 3. Информирование LLM

**Где:** `src/codelab/server/agent/context/manager.py`

**Что:** Добавлять в system prompt информацию о прочитанных файлах

**Логика:**
```python
class DefaultContextManager(ContextManager):
    async def build_context(self, session, prompt, ...):
        # ... существующая логика ...
        
        # Добавить информацию о прочитанных файлах
        if self._session_file_cache_registry is not None:
            cache = self._session_file_cache_registry.get_or_create(session_id)
            read_files = list(cache._cache.keys())
            
            if read_files:
                files_info = "\n".join([f"- {path}" for path in read_files[:20]])
                context_info = f"\n\nПрочитанные файлы (не запрашивайте повторное чтение):\n{files_info}"
                baseline.append(LLMMessage(role="system", content=context_info))
```

**Зачем:**
- LLM будет знать, какие файлы уже в контексте
- Снижать количество повторных запросов
- Улучшить качество ответов

### 4. Метрики кэша

**Где:** `src/codelab/server/observability/metrics_tracker.py`

**Что:** Добавить метрики для кэша

**Метрики:**
```python
@dataclass
class SessionMetrics:
    # ... существующие поля ...
    file_cache_hits: int = 0
    file_cache_misses: int = 0
    file_read_limit_exceeded: int = 0

class MetricsTracker:
    def record_file_cache_hit(self, session_id: str) -> None:
        metrics = self._get_or_create(session_id)
        metrics.file_cache_hits += 1
    
    def record_file_cache_miss(self, session_id: str) -> None:
        metrics = self._get_or_create(session_id)
        metrics.file_cache_misses += 1
    
    def record_file_read_limit_exceeded(self, session_id: str, path: str) -> None:
        metrics = self._get_or_create(session_id)
        metrics.file_read_limit_exceeded += 1
```

**Интеграция в FileCacheDecorator:**
```python
async def execute(self, session, arguments):
    # ... проверка кэша ...
    
    if cached_content is not None:
        if self._metrics_tracker:
            self._metrics_tracker.record_file_cache_hit(session.session_id)
        return ToolExecutionResult(...)
    
    # ... выполнение wrapped.execute() ...
    
    if self._metrics_tracker:
        self._metrics_tracker.record_file_cache_miss(session.session_id)
```

## Интеграция

### Поток выполнения

1. Пользователь отправляет промпт
2. Context Manager собирает файлы (context.gather)
3. LLM генерирует tool calls
4. Tool Executor (FileCacheDecorator) проверяет кэш:
   - Если файл в кэше → вернуть из кэша (без RPC)
   - Если нет → проверить лимит → прочитать → сохранить в кэш
5. Проверить лимиты:
   - Если превышен лимит файла → ошибка
   - Если превышен лимит итерации → ошибка
6. Вернуть результаты LLM
7. Повторить шаги 3-6 до завершения

### Точки интеграции

**FileCacheDecorator:**
- Исправить метод `execute()` для проверки кэша перед чтением
- Добавить подсчёт чтений и проверку лимитов
- Интегрировать метрики

**DefaultContextManager:**
- Добавлять информацию о прочитанных файлах в system prompt
- Вызывать в `build_context()`

**MetricsTracker:**
- Добавить методы для метрик кэша
- Интегрировать в FileCacheDecorator

**DI (`src/codelab/server/di.py`):**
- Передать `MetricsTracker` в `FileCacheDecorator`
- Передать `SessionFileCacheRegistry` в `DefaultContextManager`

## Тестирование

### Unit тесты

1. **FileCacheDecorator:**
   - Тест проверки кэша перед чтением
   - Тест сохранения в кэш после чтения
   - Тест лимитов
   - Тест метрик

2. **DefaultContextManager:**
   - Тест добавления информации в system prompt

3. **MetricsTracker:**
   - Тест метрик кэша

### Integration тесты

1. **Сценарий с повторными чтениями:**
   - Отправить промпт, требующий чтения файлов
   - Проверить, что файлы читаются только один раз
   - Проверить, что кэш работает

2. **Сценарий с превышением лимита:**
   - Отправить промпт, требующий многократного чтения
   - Проверить, что срабатывает лимит
   - Проверить, что возвращается ошибка

3. **Сценарий с LLM:**
   - Отправить промпт
   - Проверить, что system prompt содержит информацию о прочитанных файлах
   - Проверить, что LLM не запрашивает повторное чтение

## Метрики

- Количество RPC вызовов до/после
- Время выполнения tool calls до/после
- Количество повторных чтений
- Количество срабатываний лимитов
- Cache hit rate

## Риски

1. **Увеличение памяти:**
   - Кэш может занимать много памяти
   - Решение: ограничить размер кэша (1000 файлов, уже реализовано)

2. **Устаревание кэша:**
   - Файл может измениться между чтениями
   - Решение: `InvalidationSignalBus` уже реализован для инвалидации при `fs/write`

3. **Сложность отладки:**
   - Кэш может скрывать проблемы
   - Решение: логировать все операции с кэшем (уже реализовано)

## Миграция

Не требуется, так как изменения обратно совместимы:
- Исправление FileCacheDecorator не меняет API
- Лимиты можно отключить через конфигурацию
- Метрики добавляются как опциональные
