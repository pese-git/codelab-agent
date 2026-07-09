# Руководство по проверке Фазы 4 (Инкрементальный режим)

## Что проверяется

Фаза 4 добавляет инкрементальный режим управления контекстом:
- **Гидрация** (`incremental=false`): baseline пересобирается каждый ход
- **Инкрементальный** (`incremental=true`): baseline фиксируется в эпохе, отправляются только дельты

**Ожидаемая экономия:** 50-90% токенов на длинных сессиях (20+ ходов)

---

## Подготовка

### 1. Убедитесь, что конфигурация корректна

```bash
cat ~/.codelab/codelab.toml | grep -A 10 "\[agents.context\]"
```

Должно быть:
```toml
[agents.context]
enabled = true
gather_enabled = true
incremental = true  # или false для теста гидрации
```

### 2. Проверьте, что метрики экспортируются

```bash
ls -la ~/.codelab/data/observability/metrics/
```

Должны быть файлы `YYYY-MM-DD.json`.

---

## Метод 1: Ручная проверка через логи

### Шаг 1: Запустите сервер с debug логами

```bash
cd /Users/penkovsky_sa/Projects/OpenIdeaLab/CodeLab/codelab-agent

# Для инкрементального режима
uv run codelab serve --observability-debug --log-level DEBUG

# ИЛИ для гидрации (сравнение)
# Отредактируйте ~/.codelab/codelab.toml: incremental = false
# uv run codelab serve --observability-debug --log-level DEBUG
```

### Шаг 2: Выполните 10-20 запросов через клиент

Используйте любой ACP-клиент или codelab CLI для выполнения запросов.

### Шаг 3: Анализируйте логи

Ищите следующие паттерны:

**Инкрементальный режим:**
```
context.build.mode=incremental
epoch.started                              # Один раз в начале
reconciler.reconcile.unchanged             # Стабильный baseline
reconciler.reconcile.updated               # Обнаружены изменения
epoch.broken                               # Разрыв эпохи (редко)
```

**Гидрация:**
```
context.build.mode=hydration
# Нет epoch.started, reconciler.reconcile
```

### Шаг 4: Проверьте метрики

```bash
# Последние метрики
cat ~/.codelab/data/observability/metrics/$(date +%Y-%m-%d).json | jq 'to_entries | last | .value'
```

**Ключевые метрики для сравнения:**

| Метрика | Гидрация | Инкрементальный | Что означает |
|---------|----------|-----------------|--------------|
| `context_build_count` | N | N | Одинаковое количество сборок |
| `context_baseline_tokens` | Высокое | Низкое* | Сумма baseline токенов за все ходы |
| `context_tail_tokens` | N | N | Сумма tail токенов |
| `context_reconcile_count` | 0 | N | Количество реконсиляций |
| `context_epoch_breaks_total` | 0 | 0-2 | Разрывы эпох (должно быть мало) |
| `llm_total_input_tokens` | Высокое | Низкое | **Главная метрика экономии** |

*В инкрементальном режиме baseline токены накапливаются только при разрывах эпох.

---

## Метод 2: A/B тест через скрипт

```bash
cd /Users/penkovsky_sa/Projects/OpenIdeaLab/CodeLab/codelab-agent
python scripts/phase4_ab_test.py
```

Скрипт автоматически:
1. Запустит сессию с `incremental=false`
2. Запустит сессию с `incremental=true`
3. Сравнит метрики и покажет экономию

---

## Метод 3: Быстрая проверка через Python

```python
import json
from pathlib import Path
from datetime import datetime

# Читаем метрики
metrics_file = Path.home() / ".codelab/data/observability/metrics" / f"{datetime.now():%Y-%m-%d}.json"
data = json.loads(metrics_file.read_text())

# Находим сессии
for session_id, metrics in data.items():
    print(f"\nСессия: {session_id}")
    print(f"  Сборок контекста: {metrics.get('context_build_count', 0)}")
    print(f"  Реконсиляций: {metrics.get('context_reconcile_count', 0)}")
    print(f"  Разрывов эпох: {metrics.get('context_epoch_breaks_total', 0)}")
    print(f"  Baseline токенов: {metrics.get('context_baseline_tokens', 0):,}")
    print(f"  Tail токенов: {metrics.get('context_tail_tokens', 0):,}")
    print(f"  LLM токенов: {metrics.get('llm_total_input_tokens', 0):,}")
```

---

## Ожидаемые результаты

### Сценарий: 20 ходов, стабильный baseline

**Гидрация:**
```
Ход 1:  baseline=5000 + tail=500 = 5500 токенов
Ход 2:  baseline=5000 + tail=500 = 5500 токенов
...
Ход 20: baseline=5000 + tail=500 = 5500 токенов

Итого: 110 000 токенов
```

**Инкрементальный:**
```
Ход 1:  baseline=5000 + tail=500 = 5500 токенов (новая эпоха)
Ход 2:  baseline=0 + tail=500 = 500 токенов (стабильная эпоха)
...
Ход 20: baseline=0 + tail=500 = 500 токенов

Итого: 15 000 токенов
```

**Экономия:** ~86%

### Сценарий: 20 ходов, 2 разрыва эпох

**Инкрементальный с разрывами:**
```
Ход 1:   baseline=5000 + tail=500 = 5500 (эпоха 1)
Ход 2-9: baseline=0 + tail=500 = 500 (стабильно)
Ход 10:  baseline=5000 + tail=500 = 5500 (разрыв, эпоха 2)
Ход 11-15: baseline=0 + tail=500 = 500 (стабильно)
Ход 16:  baseline=5000 + tail=500 = 5500 (разрыв, эпоха 3)
Ход 17-20: baseline=0 + tail=500 = 500 (стабильно)

Итого: 25 000 токенов
```

**Экономия:** ~77% (даже с разрывами)

---

## Проверка корректности работы

### 1. Детерминизм fingerprint

В логах ищите:
```
context.build.fingerprint.computed fingerprint=abc123...
```

Одинаковый baseline должен давать одинаковый fingerprint.

### 2. Реакция на изменения файлов

Выполните `fs/write` в клиенте и проверьте логи:
```
reconciler.file_invalidated path=test.py
context_manager.file_invalidated.refreshed path=test.py
reconciler.reconcile.updated changed_sources=["test.py"]
```

Если файл в baseline:
```
epoch.broken old_epoch_id=... new_epoch_id=...
```

### 3. Лимит разрывов

Намеренно измените baseline несколько раз за ход. Должно быть:
```
epoch.break_limit_reached breaks_this_turn=1
```

---

## Troubleshooting

### Проблема: Экономия низкая (<20%)

**Возможные причины:**
1. **Частые разрывы эпох** — проверьте `context_epoch_breaks_total`
   - Решение: минимизируйте изменения system_prompt, skill_catalog
2. **Короткая сессия** — недостаточно ходов для накопления экономии
   - Решение: выполните 20+ ходов
3. **Режим гидрации** — проверьте `incremental=true` в конфиге

### Проблема: Разрывы эпох на каждом ходу

**Возможные причины:**
1. **Изменение system_prompt** — проверяется на каждом ходу
2. **Изменение skill_catalog** — проверяется на каждом ходу
3. **Недетерминированный fingerprint** — баг в коде

**Решение:** Проверьте логи `reconciler.reconcile` и найдите `changed_sources`.

### Проблема: Метрики не экспортируются

**Решение:**
1. Проверьте `observability.enabled=true` в конфиге
2. Запустите с `--observability-debug`
3. Проверьте директорию `~/.codelab/data/observability/metrics/`

---

## Дополнительные проверки

### Проверка интеграции FileCacheDecorator

```bash
# В логах ищите:
file_cache_set path=test.py              # fs/read → кэш
file_cache_invalidate path=test.py       # fs/write → инвалидация
```

### Проверка SessionFileCacheRegistry

```bash
# В логах ищите:
file_cache_created session_id=...        # Создание кэша для сессии
file_cache_closed session_id=...         # Закрытие кэша при завершении
```

### Проверка двойной защиты детекта

Измените файл через `fs/write` и проверьте, что:
1. `FileCacheDecorator` публикует сигнал в `InvalidationSignalBus`
2. `DefaultContextReconciler.on_file_invalidated()` получит сигнал
3. `ContextSnapshot.diff()` обнаружит изменение через Codec-сравнение

Оба пути должны сработать.

---

## Успешное завершение

Фаза 4 работает корректно, если:
- ✓ Экономия токенов >50% на сессиях 20+ ходов
- ✓ `context_epoch_breaks_total` минимально (0-2 за сессию)
- ✓ `reconciler.reconcile.unchanged` преобладает над `updated`
- ✓ Изменения файлов корректно обнаруживаются и обрабатываются
- ✓ Нет тихого рассинхрона baseline
