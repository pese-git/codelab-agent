## Tasks

### 1. FileSpanExporter

- [ ] 1.1 Создать `codelab/src/codelab/server/observability/exporters/file_span_exporter.py`
- [ ] 1.2 Реализовать `export_spans(spans: list[SpanContext], export_dir: str)` — запись в JSON
- [ ] 1.3 Формат файла: `spans/YYYY-MM-DD-HH-MM-SS.json` (один файл на flush)
- [ ] 1.4 Реализовать ротацию файлов при достижении max_file_size
- [ ] 1.5 Написать тесты: экспорт span'ов в файл
- [ ] 1.6 Написать тесты: ротация файлов

### 2. FileEventExporter

- [ ] 2.1 Создать `codelab/src/codelab/server/observability/exporters/file_event_exporter.py`
- [ ] 2.2 Реализовать `export_events(events: list[TimelineEvent], export_dir: str)` — запись в JSON
- [ ] 2.3 Формат файла: `events/YYYY-MM-DD.json` (один файл на день)
- [ ] 2.4 Append mode — добавление событий в существующий файл дня
- [ ] 2.5 Написать тесты: экспорт событий в файл
- [ ] 2.6 Написать тесты: append mode

### 3. FileMetricsExporter

- [ ] 3.1 Создать `codelab/src/codelab/server/observability/exporters/file_metrics_exporter.py`
- [ ] 3.2 Реализовать `export_metrics(metrics: dict[str, SessionMetrics], export_dir: str)` — запись в JSON
- [ ] 3.3 Формат файла: `metrics/YYYY-MM-DD.json` (один файл на день)
- [ ] 3.4 Написать тесты: экспорт метрик в файл

### 4. ObservabilityConfig

- [ ] 4.1 Добавить `ObservabilityConfig` в `codelab/src/codelab/server/config.py`
- [ ] 4.2 Поля: `enabled: bool = True`, `export_dir: str = "~/.codelab/data/observability"`, `flush_interval: int = 60`, `max_file_size: int = 10485760`
- [ ] 4.3 Добавить `observability: ObservabilityConfig` в `AppConfig`
- [ ] 4.4 Написать тесты: конфигурация с defaults
- [ ] 4.5 Написать тесты: загрузка из codelab.toml

### 5. Интеграция в DI

- [ ] 5.1 Обновить `ObservabilityProvider` — создание экспортеров
- [ ] 5.2 Подключить экспортеры к Tracer, EventTimeline, MetricsTracker
- [ ] 5.3 Реализовать periodic flush через asyncio timer
- [ ] 5.4 Реализовать flush при завершении сессии
- [ ] 5.5 Написать тесты: интеграция экспортеров

### 6. Тесты интеграции

- [ ] 6.1 Тест: полный цикл — span → exporter → файл
- [ ] 6.2 Тест: полный цикл — event → exporter → файл
- [ ] 6.3 Тест: полный цикл — metrics → exporter → файл
- [ ] 6.4 Тест: periodic flush работает корректно
- [ ] 6.5 Тест: flush при завершении сессии
