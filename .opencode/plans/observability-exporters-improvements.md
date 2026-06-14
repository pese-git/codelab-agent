# План улучшения observability exporters

## Обзор

Реализация полного варианта с `mark_exported(count)` + `clear_exported()` для гибкости поддержки нескольких экспортеров и точного контроля над удалением экспортированных данных.

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    Tracer / EventTimeline                    │
├─────────────────────────────────────────────────────────────┤
│  _completed_spans: list[SpanContext]                        │
│  _exported_count: int  ← НОВОЕ: количество экспортированных │
├─────────────────────────────────────────────────────────────┤
│  get_completed_spans() → list[SpanContext]                  │
│  mark_exported(count: int) → None  ← НОВОЕ                  │
│  clear_exported() → None  ← НОВОЕ                           │
│  clear() → None  # Удалить всё (для тестов/shutdown)        │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    FileSpanExporter                          │
├─────────────────────────────────────────────────────────────┤
│  _ensure_dir() → None  ← Ленивое создание директории        │
│  export_spans(spans) → Path | None                          │
│  flush(tracer) → Path | None                                │
│    1. spans = tracer.get_completed_spans()                  │
│    2. if not spans: return None                             │
│    3. result = self.export_spans(spans)                     │
│    4. if result: tracer.mark_exported(len(spans))           │
│    5. if result: tracer.clear_exported()                    │
│    6. return result                                         │
│  cleanup(max_age_days) → int  ← Удаление старых файлов      │
│  get_metrics() → ExportMetrics  ← Метрики экспорта          │
└─────────────────────────────────────────────────────────────┘
```

---

## Фаза 1: Критические исправления

### 1.1 Изменения в Tracer

**Файл:** `codelab/src/codelab/server/observability/tracer.py`

**Изменения:**
1. Добавить поле `_exported_count: int = 0`
2. Добавить метод `mark_exported(count: int) -> None`
3. Добавить метод `clear_exported() -> None`
4. **НЕ изменять** `flush()` — он не должен очищать данные

```python
class Tracer:
    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self._active_spans: list[SpanContext] = []
        self._completed_spans: list[SpanContext] = []
        self._exported_count: int = 0  # НОВОЕ

    def mark_exported(self, count: int) -> None:
        """Отметить количество экспортированных span'ов.
        
        Вызывается экспортером после успешного экспорта.
        Отмечает первые N завершённых span'ов как экспортированные.
        
        Args:
            count: Количество экспортированных span'ов.
        """
        self._exported_count = min(count, len(self._completed_spans))

    def clear_exported(self) -> None:
        """Удалить экспортированные span'ы.
        
        Удаляет только завершённые span'ы, которые были экспортированы.
        Активные span'ы не затрагиваются.
        """
        if self._exported_count > 0:
            self._completed_spans = self._completed_spans[self._exported_count:]
            self._exported_count = 0
```

### 1.2 Изменения в EventTimeline

**Файл:** `codelab/src/codelab/server/observability/event_timeline.py`

**Изменения:**
1. Добавить поле `_exported_count: int = 0`
2. Добавить метод `mark_exported(count: int) -> None`
3. Добавить метод `clear_exported() -> None`
4. **Изменить** `clear()` — НЕ отписываться от шины, только очищать события

```python
class EventTimeline:
    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self._events: list[TimelineEvent] = []
        self._subscriptions: list[Any] = []
        self._exported_count: int = 0  # НОВОЕ

    def mark_exported(self, count: int) -> None:
        """Отметить количество экспортированных событий.
        
        Args:
            count: Количество экспортированных событий.
        """
        self._exported_count = min(count, len(self._events))

    def clear_exported(self) -> None:
        """Удалить экспортированные события.
        
        Удаляет только события, которые были экспортированы.
        Подписки на EventBus не затрагиваются.
        """
        if self._exported_count > 0:
            self._events = self._events[self._exported_count:]
            self._exported_count = 0

    def clear(self) -> None:
        """Очистить все события.
        
        НЕ отписывается от шины (подписки сохраняются).
        """
        self._events.clear()
        self._exported_count = 0
        # НЕ очищаем self._subscriptions
```

### 1.3 Изменения в FileSpanExporter

**Файл:** `codelab/src/codelab/server/observability/exporters/file_span_exporter.py`

**Изменения:**
1. Убрать `mkdir` из `__init__`
2. Добавить `_ensure_dir()` метод
3. Изменить `flush()` — вызывать `mark_exported()` и `clear_exported()`
4. Добавить `cleanup(max_age_days)` метод
5. Добавить `ExportMetrics` dataclass
6. Добавить `get_metrics()` метод

```python
@dataclass
class ExportMetrics:
    """Метрики экспорта."""
    total_exports: int = 0
    failed_exports: int = 0
    total_items_exported: int = 0
    last_export_time: float | None = None
    last_export_size_bytes: int = 0


class FileSpanExporter:
    def __init__(
        self,
        export_dir: str = "~/.codelab/data/observability",
        max_file_size: int = 10485760,
    ) -> None:
        self.export_dir = Path(export_dir).expanduser() / "spans"
        self.max_file_size = max_file_size
        self._metrics = ExportMetrics()
        # НЕ создаём директорию здесь — ленивое создание

    def _ensure_dir(self) -> None:
        """Создать директорию при первом экспорте."""
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def flush(self, tracer) -> Path | None:
        """Получить завершённые span'ы из Tracer и экспортировать."""
        from codelab.server.observability.tracer import Tracer

        if not isinstance(tracer, Tracer):
            return None

        spans = tracer.get_completed_spans()
        if not spans:
            return None

        result = self.export_spans(spans)

        if result is not None:
            # Успешный экспорт — отметить и очистить экспортированные
            tracer.mark_exported(len(spans))
            tracer.clear_exported()

        return result

    def cleanup(self, max_age_days: int = 30) -> int:
        """Удалить файлы старше max_age_days.
        
        Returns:
            Количество удалённых файлов.
        """
        from datetime import datetime, timedelta
        
        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0
        
        for file in self.export_dir.glob("*.json"):
            file_time = datetime.fromtimestamp(file.stat().st_mtime)
            if file_time < cutoff:
                file.unlink()
                removed += 1
        
        # Также удаляем .rotated файлы
        for file in self.export_dir.glob("*.rotated"):
            file.unlink()
            removed += 1
        
        return removed

    def get_metrics(self) -> ExportMetrics:
        """Получить метрики экспорта."""
        return self._metrics
```

### 1.4 Изменения в FileEventExporter

**Файл:** `codelab/src/codelab/server/observability/exporters/file_event_exporter.py`

**Изменения:**
1. Убрать `mkdir` из `__init__`
2. Добавить `_ensure_dir()` метод
3. Изменить `flush()` — вызывать `mark_exported()` и `clear_exported()`
4. Исправить проверку `tmp_path`
5. Добавить ротацию по размеру
6. Добавить `cleanup(max_age_days)` метод
7. Добавить `ExportMetrics` dataclass
8. Добавить `get_metrics()` метод

```python
@dataclass
class ExportMetrics:
    """Метрики экспорта."""
    total_exports: int = 0
    failed_exports: int = 0
    total_items_exported: int = 0
    last_export_time: float | None = None
    last_export_size_bytes: int = 0


class FileEventExporter:
    def __init__(self, export_dir: str = "~/.codelab/data/observability") -> None:
        self.export_dir = Path(export_dir).expanduser() / "events"
        self._metrics = ExportMetrics()
        # НЕ создаём директорию здесь

    def _ensure_dir(self) -> None:
        """Создать директорию при первом экспорте."""
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def flush(self, timeline) -> Path | None:
        """Получить события из EventTimeline и экспортировать."""
        from codelab.server.observability.event_timeline import EventTimeline

        if not isinstance(timeline, EventTimeline):
            return None

        events = timeline.get_events()
        if not events:
            return None

        result = self.export_events(events)

        if result is not None:
            # Успешный экспорт — отметить и очистить экспортированные
            timeline.mark_exported(len(events))
            timeline.clear_exported()

        return result

    def cleanup(self, max_age_days: int = 30) -> int:
        """Удалить файлы старше max_age_days."""
        from datetime import datetime, timedelta
        
        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0
        
        for file in self.export_dir.glob("*.json"):
            file_time = datetime.fromtimestamp(file.stat().st_mtime)
            if file_time < cutoff:
                file.unlink()
                removed += 1
        
        return removed

    def get_metrics(self) -> ExportMetrics:
        """Получить метрики экспорта."""
        return self._metrics
```

---

## Фаза 2: Ротация и очистка

### 2.1 Ротация span файлов по размеру

**Файл:** `file_span_exporter.py`

```python
def _rotate_if_needed(self, file_path: Path) -> None:
    """Ротировать файл если он превышает max_file_size."""
    try:
        file_size = file_path.stat().st_size
        if file_size > self.max_file_size:
            # Переименовываем файл с суффиксом .rotated
            rotated_path = file_path.with_suffix(f"{file_path.suffix}.rotated")
            file_path.rename(rotated_path)
            logger.info("Rotated span file: %s -> %s", file_path, rotated_path)
    except Exception as e:
        logger.warning("Failed to rotate span file %s: %s", file_path, e)
```

### 2.2 Ротация event файлов по размеру

**Файл:** `file_event_exporter.py`

```python
def _rotate_if_needed(self, file_path: Path, max_file_size: int = 10485760) -> Path:
    """Ротировать файл если он превышает max_file_size.
    
    Returns:
        Путь к актуальному файлу (новому если была ротация).
    """
    if file_path.stat().st_size <= max_file_size:
        return file_path
    
    # Архивировать текущий файл
    archive_name = file_path.stem + f"_{datetime.now().strftime('%H%M%S')}"
    archive_path = file_path.with_name(archive_name + file_path.suffix)
    file_path.rename(archive_path)
    logger.info("Rotated event file: %s -> %s", file_path, archive_path)
    
    # Возвращаем путь к новому файлу (который будет создан)
    return file_path
```

### 2.3 Очистка старых файлов

**Файлы:** `file_span_exporter.py`, `file_event_exporter.py`

```python
def cleanup(self, max_age_days: int = 30) -> int:
    """Удалить файлы старше max_age_days.
    
    Returns:
        Количество удалённых файлов.
    """
    from datetime import datetime, timedelta
    
    cutoff = datetime.now() - timedelta(days=max_age_days)
    removed = 0
    
    for file in self.export_dir.glob("*.json"):
        file_time = datetime.fromtimestamp(file.stat().st_mtime)
        if file_time < cutoff:
            file.unlink()
            removed += 1
    
    # Также удаляем .rotated файлы
    for file in self.export_dir.glob("*.rotated"):
        file.unlink()
        removed += 1
    
    return removed
```

---

## Фаза 3: Метрики экспорта

### 3.1 ExportMetrics dataclass

**Файлы:** `file_span_exporter.py`, `file_event_exporter.py`

```python
@dataclass
class ExportMetrics:
    """Метрики экспорта."""
    total_exports: int = 0
    failed_exports: int = 0
    total_items_exported: int = 0
    last_export_time: float | None = None
    last_export_size_bytes: int = 0
```

### 3.2 Обновление метрик в экспортерах

**Файл:** `file_span_exporter.py`

```python
def export_spans(self, spans: list[SpanContext]) -> Path | None:
    """Экспортировать список span'ов в JSON файл."""
    if not spans:
        return None

    self._ensure_dir()

    # ... экспорт ...

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Обновляем метрики
        self._metrics.total_exports += 1
        self._metrics.total_items_exported += len(spans)
        self._metrics.last_export_time = time.time()
        self._metrics.last_export_size_bytes = file_path.stat().st_size

        return file_path
    except Exception as e:
        self._metrics.failed_exports += 1
        logger.error("Failed to export spans: %s", e)
        return None
```

---

## Фаза 4: Валидация данных

### 4.1 Валидация span'ов

**Файл:** `file_span_exporter.py`

```python
def _validate_spans(self, spans: list[SpanContext]) -> list[SpanContext]:
    """Валидировать span'ы перед экспортом.
    
    Пропускает:
    - Span'ы без span_id
    - Span'ы без end_time (активные)
    
    Args:
        spans: Список span'ов для валидации.
    
    Returns:
        Список валидных span'ов.
    """
    valid = []
    for span in spans:
        if not span.span_id:
            logger.warning("Skipping span without span_id")
            continue
        if span.end_time is None:
            logger.debug("Skipping active span: %s", span.span_id)
            continue
        valid.append(span)
    return valid
```

### 4.2 Валидация событий

**Файл:** `file_event_exporter.py`

```python
def _validate_events(self, events: list[TimelineEvent]) -> list[TimelineEvent]:
    """Валидировать события перед экспортом.
    
    Пропускает:
    - События без event_type
    - События без timestamp
    
    Args:
        events: Список событий для валидации.
    
    Returns:
        Список валидных событий.
    """
    valid = []
    for event in events:
        if not event.event_type:
            logger.warning("Skipping event without event_type")
            continue
        if event.timestamp == 0:
            logger.debug("Skipping event with zero timestamp")
            continue
        valid.append(event)
    return valid
```

---

## Порядок реализации

| Фаза | Задач | Приоритет | Зависимости |
|------|-------|-----------|-------------|
| **Фаза 1** | Критические исправления | 🔴 Критический | — |
| 1.1 | Tracer: mark_exported + clear_exported | 🔴 Критический | — |
| 1.2 | EventTimeline: mark_exported + clear_exported | 🔴 Критический | — |
| 1.3 | FileSpanExporter: flush + cleanup + metrics | 🔴 Критический | 1.1 |
| 1.4 | FileEventExporter: flush + cleanup + metrics | 🔴 Критический | 1.2 |
| **Фаза 2** | Ротация и очистка | 🟡 Средний | Фаза 1 |
| 2.1 | Span files: ротация по размеру | 🟡 Средний | 1.3 |
| 2.2 | Event files: ротация по размеру | 🟡 Средний | 1.4 |
| 2.3 | Cleanup: удаление старых файлов | 🟡 Средний | 1.3, 1.4 |
| **Фаза 3** | Метрики экспорта | 🟢 Низкий | Фаза 1 |
| 3.1 | ExportMetrics dataclass | 🟢 Низкий | 1.3, 1.4 |
| 3.2 | Обновление метрик в экспортерах | 🟢 Низкий | 3.1 |
| **Фаза 4** | Валидация данных | 🟢 Низкий | Фаза 1 |
| 4.1 | Валидация span'ов | 🟢 Низкий | 1.3 |
| 4.2 | Валидация событий | 🟢 Низкий | 1.4 |

---

## Тесты

### Unit тесты

**Tracer:**
- `test_mark_exported_updates_count`
- `test_clear_exported_removes_exported_spans`
- `test_clear_exported_preserves_active_spans`
- `test_clear_exported_with_zero_count`

**EventTimeline:**
- `test_mark_exported_updates_count`
- `test_clear_exported_removes_exported_events`
- `test_clear_exported_preserves_subscriptions`
- `test_clear_does_not_clear_subscriptions`

**FileSpanExporter:**
- `test_flush_calls_mark_exported_and_clear_exported`
- `test_cleanup_removes_old_files`
- `test_cleanup_removes_rotated_files`
- `test_metrics_updated_on_success`
- `test_metrics_updated_on_failure`
- `test_validate_spans_filters_invalid`

**FileEventExporter:**
- `test_flush_calls_mark_exported_and_clear_exported`
- `test_cleanup_removes_old_files`
- `test_metrics_updated_on_success`
- `test_validate_events_filters_invalid`

### Интеграционные тесты

- `test_full_export_cycle_with_multiple_flushes`
- `test_export_with_rotation`
- `test_cleanup_removes_old_files`
- `test_metrics_accuracy`

---

## Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Потеря данных при сбое | Низкая | Высокое | Атомарная запись через tempfile |
| Race condition | Низкая | Среднее | mark_exported + clear_exported |
| Memory leak | Средняя | Среднее | Периодический flush + cleanup |
| Disk full | Низкая | Высокое | Ограничение max_file_size + cleanup |

---

## Метрики успеха

- [ ] Все unit тесты проходят
- [ ] Все интеграционные тесты проходят
- [ ] `mark_exported()` и `clear_exported()` работают корректно
- [ ] Ротация файлов работает по размеру
- [ ] Очистка старых файлов работает
- [ ] Метрики экспорта обновляются корректно
- [ ] Валидация данных работает
- [ ] Нет потери данных при сбое
- [ ] Нет race condition при параллельном экспорте
