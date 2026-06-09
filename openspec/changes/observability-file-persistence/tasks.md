## Tasks

### 1. FileSpanExporter

- [x] 1.1 Создать `codelab/src/codelab/server/observability/exporters/file_span_exporter.py`
- [x] 1.2 Реализовать `export_spans(spans: list[SpanContext], export_dir: str)` — запись в JSON
- [x] 1.3 Формат файла: `spans/YYYY-MM-DD-HH-MM-SS.json` (один файл на flush)
- [x] 1.4 Реализовать ротацию файлов при достижении max_file_size
- [x] 1.5 Написать тесты: экспорт span'ов в файл
- [x] 1.6 Написать тесты: ротация файлов

### 2. FileEventExporter

- [x] 2.1 Создать `codelab/src/codelab/server/observability/exporters/file_event_exporter.py`
- [x] 2.2 Реализовать `export_events(events: list[TimelineEvent], export_dir: str)` — запись в JSON
- [x] 2.3 Формат файла: `events/YYYY-MM-DD.json` (один файл на день)
- [x] 2.4 Append mode — добавление событий в существующий файл дня
- [x] 2.5 Написать тесты: экспорт событий в файл
- [x] 2.6 Написать тесты: append mode

### 3. FileMetricsExporter

- [x] 3.1 Создать `codelab/src/codelab/server/observability/exporters/file_metrics_exporter.py`
- [x] 3.2 Реализовать `export_metrics(metrics: dict[str, SessionMetrics], export_dir: str)` — запись в JSON
- [x] 3.3 Формат файла: `metrics/YYYY-MM-DD.json` (один файл на день)
- [x] 3.4 Написать тесты: экспорт метрик в файл

### 4. ObservabilityConfig

- [x] 4.1 Добавить `ObservabilityConfig` в `codelab/src/codelab/server/config.py`
- [x] 4.2 Поля: `enabled: bool = True`, `export_dir: str = "~/.codelab/data/observability"`, `flush_interval: int = 60`, `max_file_size: int = 10485760`
- [x] 4.3 Добавить `observability: ObservabilityConfig` в `AppConfig`
- [x] 4.4 Написать тесты: конфигурация с defaults
- [x] 4.5 Написать тесты: загрузка из codelab.toml

### 5. Интеграция в DI

- [x] 5.1 Обновить `ObservabilityProvider` — создание экспортеров
- [x] 5.2 Подключить экспортеры к Tracer, EventTimeline, MetricsTracker
- [x] 5.3 Реализовать periodic flush через asyncio timer
- [x] 5.4 Реализовать flush при завершении сессии
- [x] 5.5 Написать тесты: интеграция экспортеров

### 6. Тесты интеграции

- [x] 6.1 Тест: полный цикл — span → exporter → файл
- [x] 6.2 Тест: полный цикл — event → exporter → файл
- [x] 6.3 Тест: полный цикл — metrics → exporter → файл
- [x] 6.4 Тест: periodic flush работает корректно
- [x] 6.5 Тест: flush при завершении сессии

### 7. Исправление бага с event_bus режимом

- [x] 7.1 Передать `config.agents.use_event_bus` напрямую в `LLMLoopStage` как `bool`
- [x] 7.2 Упростить `_should_use_event_bus()` — возвращать `self._use_event_bus`
- [x] 7.3 Обновить `PipelineProvider` в DI — добавить `config` параметр
- [x] 7.4 Убрать `use_event_bus_default` из `SessionFactory` (не нужен)
