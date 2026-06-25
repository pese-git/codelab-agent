# Phase 2 — Слой хранения C (спецификация для разработки)

> **Статус:** Готово к разработке после Phase 0/1 — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Длительность:** 2 недели
> **Цель:** дать слою C измеримую эффективность — точный подсчёт токенов (`TokenCounter`), устранение дублирующих ACP RPC на чтение файлов (`FileContentCache` + `SessionFileCacheRegistry` + `FileCacheDecorator`) и **детерминированное** скелетирование кода (`CodeSkeletonizer`), закладывающее стабильность baseline под будущий prompt-cache хит.

Phase 2 реализует ABC слоя C, замороженные в Phase 0. Опирается на
[INTERFACES.md §4](./INTERFACES.md) (контракты `TokenCounter`, `CodeSkeletonizer`,
`FileContentCache`, `ContextCompactor`), [DATA_MODELS.md §3](./DATA_MODELS.md) (`ContextItem`)
и [CONSOLIDATED_ARCHITECTURE.md §3 (Слой C), §6 (кэширование), §7 (сжатие)](./CONSOLIDATED_ARCHITECTURE.md).

---

## Задачи

### T2.1 — `TokenCounter` (tiktoken + fallback)
- Реализовать `TokenCounter(ABC)` из [INTERFACES.md §4](./INTERFACES.md): `count(text)` и `count_messages(messages)`.
- Бэкенд по умолчанию — `tiktoken` (под флагом `use_tiktoken=True` из `ContextConfig`); кодировка кэшируется на процесс.
- **Fallback** при недоступности `tiktoken` (нет пакета / неизвестная модель): эвристика `len(text) / 4` с явным WARNING-логом, без падения.
- `count_messages()` учитывает служебный overhead роли/разделителей сообщений (как в legacy-оценке `context_compactor`).
- **Acceptance:** на эталонных строках расхождение с reference-tiktoken = 0 токенов; при `use_tiktoken=False` или отсутствии пакета используется fallback и логируется WARNING; `count_messages([])==0`; unit-тесты на overhead сообщений.

### T2.2 — `FileContentCache` + `SessionFileCacheRegistry`
- Реализовать `FileContentCache(ABC)`: `get(path)`, `set(path, content)`, `invalidate(path)`. In-memory кэш на сессию с лимитом `cache_max_files` (LRU-эвикция по `last_accessed`).
- `SessionFileCacheRegistry` (конкретный компонент, не ABC) — фабрика/реестр кэшей по `session_id`: один `FileContentCache` на сессию, изоляция между сессиями, очистка при завершении сессии.
- `invalidate(path)` **ОБЯЗАН** публиковать сигнал изменения файла в **единый источник истины** об изменениях (см. T2.4 и [§6 кэширование](./CONSOLIDATED_ARCHITECTURE.md)) — не только сбрасывать локальную запись.
- **Acceptance:** `get` после `set` возвращает контент; после `invalidate` — `None`; превышение `cache_max_files` вытесняет наименее недавно использованный; кэши разных сессий не пересекаются; `invalidate` публикует событие в единый источник истины (проверяется подписчиком-моком).

### T2.3 — `FileCacheDecorator` (read-cache + write-invalidation поверх ACP)
- Реализовать `FileCacheDecorator` (конкретный компонент) — обёртку над операциями чтения/записи файлов, выполняющую **весь I/O строго через ACP `ToolRegistry`** (`read_file` / `write_file`), без прямого доступа к ФС.
- **Read-path:** при `read_file(path)` сначала `cache.get(path)`; промах → ACP RPC `read_file` → `cache.set`. Повторное чтение того же пути в пределах сессии — **кэш-хит без RPC**.
- **Write-path:** при `write_file(path, …)` после успешного ACP RPC вызвать `cache.invalidate(path)` (write-invalidation), чтобы следующее чтение перечитало актуальное содержимое и опубликовался сигнал изменения.
- **Acceptance:** первое чтение → ровно 1 ACP RPC; повторное чтение того же пути → 0 RPC (кэш-хит, проверяется счётчиком вызовов `ToolRegistry`-мока); после `write_file` следующее чтение снова делает RPC; декоратор не обращается к ФС напрямую (нет `open`/`Path.read_text`).

### T2.4 — Единый источник истины об изменениях файла (стык Phase 2 ↔ Phase 4)
- Ввести единый канал/реестр сигналов «файл изменён» (`FileChangeSignal`/наблюдаемый источник), на который пишет `FileContentCache.invalidate()` и `FileCacheDecorator` write-path.
- Зафиксировать контракт: **и `invalidate()` (Phase 2), и будущий snapshot-детект (`ContextReconciler.snapshot()`/`detect_changes()`, Phase 4) слушают ОДИН источник истины** — не два независимых механизма. Phase 4 подключает к нему детект эпохи; Phase 2 только публикует.
- **Acceptance:** существует одна точка публикации/подписки на изменения файла; подписчик-мок получает событие при `invalidate` и при write-path; задокументировано в `§6 кэширование`, что Phase 4 переиспользует этот же источник (нет дублирующего детектора).

### T2.5 — `CodeSkeletonizer` + `PythonASTSkeletonizer` (детерминированный вывод)
- Реализовать `CodeSkeletonizer(ABC)` из [INTERFACES.md §4](./INTERFACES.md): `can_handle(path)`, `skeletonize(code)`.
- `PythonASTSkeletonizer` — на `ast`: сохраняет сигнатуры классов/функций/методов, докстринги (опционально усечённые), декораторы и импорты; тела заменяет на `...`/`pass`.
- **ДЕТЕРМИНИЗМ — жёсткое требование:** один и тот же вход даёт **бит-в-бит идентичный** выход (стабильный порядок узлов, отсутствие таймстемпов/множеств/итерации по `dict` без сортировки) — это база для стабильного `baseline_fingerprint` и prompt-cache хита (см. [§7 сжатие](./CONSOLIDATED_ARCHITECTURE.md)).
- Результат скелетирования оформляется как `ContextItem` с `type=ContextType.FILE_SKELETON` ([DATA_MODELS.md §3](./DATA_MODELS.md), priority по умолчанию 3); `token_count` считается через `TokenCounter`.
- **Acceptance:** `skeletonize(code)` детерминирован (1000 прогонов → один хэш вывода); на репрезентативном корпусе экономия токенов **~85%** (порог в тесте, напр. ≥80%); `can_handle("x.py")==True`, `can_handle("x.md")==False`; невалидный Python → graceful fallback (вернуть исходник, WARNING), без исключения наружу.

### T2.6 — Интеграция слоя C и feature-флаги
- Подключить слой C к пути формирования payload за флагами `ContextConfig`: `use_tiktoken`, `file_cache`, `skeletonize`, `cache_max_files`.
- `TokenCounter` используется при заполнении `PayloadEnvelope.token_count` и `ContextItem.token_count`; `FileCacheDecorator` — в read-path `ContextGatherer` (Phase 1); скелетирование — опциональный шаг подготовки `file_content` → `file_skeleton`.
- **Acceptance:** при `file_cache=False`/`skeletonize=False`/`use_tiktoken=False` поведение деградирует корректно (RPC без кэша / полный контент / fallback-счётчик); при включённых флагах — кэш-хиты, скелеты и точный счёт наблюдаемы в метриках/логах; существующие тесты зелёные.

---

## Definition of Done для Phase 2

- [ ] `TokenCounter` (tiktoken + fallback) реализован; точность 0-токенов на эталоне, fallback без падения.
- [ ] `FileContentCache` + `SessionFileCacheRegistry` реализованы; LRU-эвикция и изоляция по сессиям работают.
- [ ] `FileCacheDecorator` делает I/O строго через ACP `ToolRegistry`; повторное чтение — кэш-хит без RPC; write → invalidation.
- [ ] Единый источник истины об изменениях файла введён; `invalidate()` и write-path публикуют в него; контракт стыка Phase 2 ↔ 4 задокументирован.
- [ ] `PythonASTSkeletonizer` детерминирован (стабильный хэш) и даёт ~85% экономии; невалидный код — graceful fallback.
- [ ] Флаги `use_tiktoken`/`file_cache`/`skeletonize`/`cache_max_files` управляют слоем C; деградация корректна.
- [ ] Все существующие тесты зелёные; типизация (mypy/pyright) проходит.

---

## Что Phase 2 НЕ делает (важно)

- Не реализует инкрементальность (`ContextEpoch`/`ContextSnapshot`/`ContextReconciler`) — это **Phase 4**. Phase 2 только **публикует** сигнал изменения в единый источник, на который Phase 4 подпишет snapshot-детект.
- Не собирает контекст (`TaskAnalyzer`/`ContextGatherer`) — это **Phase 1**; Phase 2 даёт инструменты (счётчик/кэш/скелет), которые Phase 1 использует в read-path.
- Не реализует фазы сжатия Summarize (диалоговую суммаризацию) — `ContextCompactor`/`ConversationSummarizer` за пределами слоя C здесь не трогаются.
- **Однако** детерминизм `CodeSkeletonizer` здесь — это закладка фундамента под стабильный `baseline_fingerprint` и кэш-хит, которые активируются в Phase 4.

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| Недетерминированный скелет (порядок узлов, `set`/`dict`-итерация, докстринг-обрезка по времени) → меняется `baseline_fingerprint` → инвалидация prompt-cache | Жёсткое требование детерминизма в T2.5; тест «1000 прогонов → один хэш»; запрет неупорядоченных коллекций в выводе (code-review правило) |
| Рассинхрон инвалидаций: два независимых механизма детекта изменений (кэш Phase 2 vs snapshot Phase 4) → stale-контент или ложный epoch-break | Единый источник истины (T2.4): `invalidate()` и snapshot-детект слушают ОДИН канал; запрет второго детектора закреплён в §6 |
| `FileCacheDecorator` обходит ACP и читает ФС напрямую → нарушение sandbox/прав ACP | I/O строго через `ToolRegistry` (T2.3); тест на отсутствие `open`/`Path.read_text`; code-review правило |
| `tiktoken` недоступен в окружении (пакет/модель) → падение подсчёта | Fallback `len/4` с WARNING (T2.1); флаг `use_tiktoken=False` для принудительного fallback |
| Кэш растёт неограниченно (долгие сессии, много файлов) | Лимит `cache_max_files` + LRU-эвикция (T2.2); очистка кэша при завершении сессии в `SessionFileCacheRegistry` |
| Stale-контент после внешней правки файла (вне ACP write) | Write-invalidation покрывает ACP-путь; внешние правки — зона Phase 4 (snapshot-детект через тот же единый источник) |
