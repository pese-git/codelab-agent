# Context Manager — Пример работы (agent loop, шаг за шагом)

> **Статус:** Канон (иллюстрация) — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Дата:** 25 июня 2026 (обновлено 2026-07-17: добавлены итерации 5 и 6 для Phase 5/6)
>
> Сквозной прогон: какие данные подаются на **вход**, какие **преобразования** происходят
> внутри (слои A→B→C), и что получается на **выходе** (`PayloadEnvelope`). Показаны несколько
> итераций agent loop, включая кэш файлов, скелетирование, 3-фазное сжатие, инкрементальную
> эпоху, рекурсивные зависимости (Phase 5) и child session (Phase 6).
>
> Числа токенов — иллюстративные, для наглядности пропорций. Термины и компоненты —
> из [INTERFACES.md](./INTERFACES.md) / [DATA_MODELS.md](./DATA_MODELS.md).

---

## Сценарий

Пользователь: **«Исправь падение при пустом email в авторизации».**
Проект — небольшой Python-сервис. Лимит окна: `max_context_tokens=128000`, `reserved_tokens=4096`.
Стратегия — `SingleStrategy` (`agent_scope="single"`).

Каждая итерация = один проход agent loop: `Strategy → ExecutionEngine.build_context() → ContextManager → LLM → (tool calls) → continue`.

### Обзор 4 итераций (sequence diagram)

```mermaid
sequenceDiagram
    actor U as Пользователь
    participant CM as ContextManager
    participant FC as FileContentCache
    participant L as LLM / LLMAdapter

    Note over U,L: Итерация 1 - сбор контекста (гидрация)
    U->>CM: prompt "исправь падение при пустом email"
    CM->>CM: TaskAnalyzer, Gatherer [read login.py, validators.py]
    CM->>FC: set login.py, set validators.py
    CM->>L: PayloadEnvelope baseline 3300 + tail 20 [fp_a1]
    L-->>CM: tool_call read test_login.py

    Note over U,L: Итерация 2 - продолжение (кэш-хит)
    CM->>FC: get login.py - кэш-хит [0 RPC]
    CM->>L: baseline 3300 + tail 1240 [fp_a1]
    L-->>CM: правка validators.py; read session.py [большой]

    Note over U,L: Итерация 3 - скелет + 3-фазное сжатие
    CM->>CM: skeletonize session.py 3500 to 250; Prune 135k to 52k
    CM->>L: baseline 52000 [fp_b7]
    L-->>CM: fs/write validators.py [фикс]

    Note over U,L: Итерация 4a - инкрементальная эпоха (baseline неизменен)
    CM->>CM: snapshot.diff = UNCHANGED, baseline из эпохи
    CM->>L: только tail 30 [fp_b7 - prompt-cache хит]
    L-->>CM: обычный ход

    Note over U,L: Итерация 4b - правка файла, инвалидация
    L-->>CM: fs/write validators.py
    CM->>FC: invalidate validators.py + сигнал изменения
    CM->>CM: reconcile = UPDATED, новая эпоха fp_c2
    CM->>L: baseline пересобран 52010 [fp_c2]
    L-->>U: end_turn, ответ
```

---

## Итерация 1 — первый запрос (сбор контекста, гидрация)

### Вход в `ContextManager.build_context()`
```python
session.history = []            # диалог пустой
prompt = [{"role": "user", "content": "Исправь падение при пустом email в авторизации"}]
agent_scope = "single"
system_prompt = "Ты — кодовый агент CodeLab. ..."   # ~400 токенов
```

### Преобразования внутри

**Слой A — сбор:**
1. `TaskAnalyzer.analyze()` → `TaskProfile`:
   ```python
   TaskProfile(task_type=BUG_FIX, search_terms=["email", "auth", "login"],
               target_modules=["auth"], investigation_depth=2, needs_tests=True)
   ```
2. `ContextGatherer.gather()` через ACP `ToolRegistry`:
   - `project_tree()` → дерево проекта;
   - `search(["email","auth","login"])` → кандидаты: `auth/login.py`, `auth/validators.py`;
   - `read_file()` обоих → содержимое (**кладётся в `FileContentCache`**, слой C);
   - `DependencyGraph`: `login.py` импортирует `validators.py` → оба в отборе.
   - Результат — `list[ContextItem]`:
     ```
     ContextItem(id="auth/login.py",      type=FILE_CONTENT, priority=5, tokens=1800)
     ContextItem(id="auth/validators.py", type=FILE_CONTENT, priority=5, tokens=900)
     ```

**Слой A — бюджет:** `TokenBudgetManager.allocate(128000)` → history-доля 64000 ≫ 2700 токенов файлов → усечение не требуется.

**Сборка `PayloadEnvelope`:**
- `baseline` = system_prompt + системные правила + 2 файла (стабильный префикс);
- `tail` = текущий ход (user-промпт);
- `baseline_fingerprint` = hash(baseline) = `"fp_a1"`.

### Выход
```python
PayloadEnvelope(
  baseline = [system(400t), rules(200t), file:login.py(1800t), file:validators.py(900t)],
  tail     = [user("Исправь падение...")(20t)],
  baseline_fingerprint = "fp_a1",
  token_count = 3320,
)
# to_messages() → 5 сообщений → LLM
```
**LLM-ответ:** запрашивает `fs/read` файла теста `auth/test_login.py` (tool call).

---

## Итерация 2 — продолжение после tool-результата (кэш файла)

Tool `fs/read auth/test_login.py` выполнен → результат лёг в `session.history` И в `FileContentCache`.

### Вход в `build_context()` (через `continue_execution`)
```python
session.history = [user(...), assistant(tool_call: read test_login.py), tool_result(test_login.py содержимое 1200t)]
prompt = []                     # продолжение, нового промпта нет
```

### Преобразования
- **Слой A:** `TaskAnalyzer` не перезапускается (профиль уже есть в скоупе); `ContextGatherer` видит, что `login.py`/`validators.py` уже собраны.
- **Слой C — кэш-хит:** агент в этом ходу ссылается на `login.py` повторно → `FileContentCache.get("auth/login.py")` возвращает содержимое **без нового ACP RPC** (экономия round-trip).
- **Гидрация (Phase 1):** `baseline` пересобирается заново (та же тройка файлов) → `baseline_fingerprint` снова `"fp_a1"`; `tail` пополняется tool-результатом.

### Выход
```python
PayloadEnvelope(
  baseline = [system, rules, login.py, validators.py],          # 3300t (как в итерации 1)
  tail     = [user(...), assistant(tool_call), tool_result(test_login.py 1200t)],  # 1240t
  baseline_fingerprint = "fp_a1",
  token_count = 4540,
)
```
> Без кэша повторное чтение `login.py` стоило бы ещё одного RPC к клиенту. С `FileContentCache` — 0 мс.

**LLM-ответ:** предлагает правку `validators.py` (добавить проверку пустого email), просит показать ещё один большой файл `auth/session.py` (3500 токенов).

---

## Итерация 3 — большой файл + 3-фазное сжатие

`fs/read auth/session.py` (3500t) прочитан. История растёт; добавим, что к этому ходу накопилось много старых tool-выводов (диалог длинный). Суммарно payload «распух» до ~135000 токенов — **превышает лимит**.

### Вход
```python
session.history = [ ...много ходов..., tool_result(session.py 3500t), ...старые tool_results... ]
```

### Преобразования
**Слой C — скелетирование при сборке:** `auth/session.py` не правится агентом, нужен только для структуры → `CodeSkeletonizer.skeletonize()`:
```
# было 3500 токенов:
class SessionManager:
    def create(self, user_id: str) -> Session:
        # ... 40 строк ...
    def validate(self, token: str) -> bool:
        # ... 30 строк ...

# стало ~250 токенов (детерминированный вывод):
class SessionManager:
    def create(self, user_id: str) -> Session: ...
    def validate(self, token: str) -> bool: ...
```

**`ensure_context_fits()` → `ContextCompactor.compact_if_needed()`** (превышен лимит), 3 фазы:
1. **Prune** — FIFO-удаление старых tool-выводов из середины (сохранены первые 2 и последние N сообщений): 135000 → 60000t.
2. **Skeletonize** — уже применено к `session.py` на сборке; остальные крупные read-only файлы скелетируются: 60000 → 52000t.
3. **Summarize** — не требуется (уже влезает). `ConversationSummarizer` не вызывается.

### Выход
```python
PayloadEnvelope(
  baseline = [system, rules, login.py, validators.py, session.py(СКЕЛЕТ 250t)],
  tail     = [...сжатая история: первые 2 + последние N сообщений...],
  baseline_fingerprint = "fp_b7",   # baseline изменился (добавился скелет session.py)
  token_count = 52000,
)
```
> Без скелетирования `session.py` занял бы 3500t вместо 250t; без Prune диалог бы не влез вовсе.

**LLM-ответ:** вносит правку в `validators.py` через `fs/write` (добавлена проверка пустого email).

---

## Итерация 4 — инкрементальная эпоха (Phase 4) + инвалидация после правки

С Phase 4 включён флаг `agents.context.lifecycle.incremental=true`. Эпоха уже создана (итерация 3 зафиксировала `baseline` с `fingerprint="fp_b7"`).

### 4a. Обычный ход — baseline не менялся → кэш-хит

**Вход:** новый ход, файлы не трогались.

**Преобразования (слой B):**
- `ContextReconciler.snapshot()` → текущие отпечатки источников;
- `ContextSnapshot.diff(prev)` → **пусто** (ничего не изменилось) → `ReconcileResult(state=UNCHANGED, epoch_broken=False)`;
- `baseline` берётся из активной `ContextEpoch` **как есть** (не пересобирается).

**Выход:**
```python
PayloadEnvelope(
  baseline = <тот же, fingerprint="fp_b7">,    # НЕ переотправляется заново
  tail     = [новый user-ход(30t)],            # шлётся только дельта
  baseline_fingerprint = "fp_b7",
  token_count = 52030,
)
```
> **Профит:** стабильный `fp_b7` → prompt-cache хит у провайдера. Биллится/обрабатывается только tail (30t), а не 52000t. На длинной сессии это экономия каждый ход.

### 4b. Правка файла → единый сигнал инвалидации → обновление эпохи

Агент сделал `fs/write auth/validators.py` (применил фикс).

**Преобразования:**
1. `FileCacheDecorator` перехватывает успешный `fs/write` → `FileContentCache.invalidate("auth/validators.py")` **и публикует сигнал «файл изменён» в единый источник истины** (стык Phase 2↔4).
2. На границе хода `ContextReconciler.reconcile()`:
   - `ContextSnapshot.diff()` ловит изменение `validators.py` (через тот же сигнал, не таймстемп);
   - `ReconcileResult(state=UPDATED, updated_sources=["auth/validators.py"], epoch_broken=True)`;
   - `baseline` пересобирается с новой версией `validators.py` → новый `fingerprint="fp_c2"`.

**Выход:**
```python
PayloadEnvelope(
  baseline = [system, rules, login.py, validators.py(НОВАЯ версия), session.py(скелет)],
  baseline_fingerprint = "fp_c2",   # эпоха обновлена
  tail     = [tool_result(write ok)(10t)],
  token_count = 52010,
)
```
> Ключевой инвариант: правка файла **дошла и до кэша, и до эпохи** через один сигнал. Не будет ситуации, когда модель видит старую версию `validators.py` (тихий баг рассинхрона, который предотвращает требование Phase 2↔4).

---

## Итерация 5 — рекурсивные зависимости (Phase 5)

Включён `agents.context.gather.recursive_dependencies=true`. `TaskAnalyzer`
выставил `investigation_depth=3` (сложный рефакторинг — агент смотрит глубоко).

`auth/validators.py` импортирует `auth/login.py` импортирует `auth/utils.py`
импортирует `auth/constants.py` — цепочка 3 уровня.

### Вход

```python
session.history = [...предыдущие ходы...]
prompt = [{"role": "user", "content": "Отрефактори валидаторы: разнеси по слоям"}]
```

### Преобразования

**Слой A — Phase 5:**
1. `ContextGatherer.gather()` читает `auth/validators.py` и парсит импорты (regex: Python + Dart).
2. `dependency_graph.parse_imports(content)` → `["auth.login", "auth.utils"]`.
3. `dependency_graph.add_file("auth/validators.py", ["auth/login.py", "auth/utils.py"])`.
4. `set_max_depth(investigation_depth=3)` — настраиваем граф.
5. `_get_dependents(items, profile)`:
   - для каждого `item` вызывает `get_dependents()` (reverse: кто импортирует) +
     `get_dependencies(recursive=True, max_depth=3)` (forward: транзитивные).
6. `get_dependencies("auth/validators.py", recursive=True)`:
   - depth=0: validators → [login, utils]
   - depth=1: login → [utils], utils → [constants]
   - depth=2: constants → (нет импортов)
   - visited-set защищает от циклов.
   - Результат: `["auth/login.py", "auth/utils.py", "auth/constants.py"]`.

### Выход

```python
# Граф зависимостей после итерации 5:
# validators.py → login.py, utils.py
# login.py → utils.py
# utils.py → constants.py
# constants.py → (нет)

# В контекст попали:
#   auth/validators.py  (target)
#   auth/login.py       (depth 1)
#   auth/utils.py       (depth 1)
#   auth/constants.py   (depth 2)
```

```
context.gather.dependents.resolved  dependents_count=3  recursive_mode=True
                                    max_depth=3  graph_stats={files_in_graph: 4,
                                    total_dependencies: 4, total_dependents: 0}
```

> **Без `recursive_dependencies=true`** в контекст попал бы только `validators.py`
> (target), и LLM пришлось бы самому делать `fs/read` для `login.py`/`utils.py`/
> `constants.py` — лишние round-trips.

**Лог:** `context.gather.file.imports_parsed` для каждого файла (список импортов).

---

## Итерация 6 — мультиагент: child session (Phase 6)

Стратегия (когда будет реализована) или прямой тест-multimodal создаёт **child session**
для субагента, который решает изолированную подзадачу (например, анализ логов).

### Вход

```python
subagent_scope = "log-analyzer"
parent_session_id = "sess_main"
```

### Преобразования

**Слой D — Phase 6:**
1. `ChildSessionManager.create_child(parent, "log-analyzer")`:
   - генерирует `child_session_id = "sess_main_child_log-analyzer"` через `SessionFactory.create_session(cwd=parent.cwd, session_id=...)`;
   - сохраняет `parent_session_id` и `subagent_scope` в `config_values`;
   - вызывает `SessionStorage.save_session(child_state)`.
2. Субагент работает в изоляции: свой `agent_scope`, свой `ContextEpoch`, свой `FileContentCache`.
3. После завершения субагента: `collect_summary(child)`:
   - `history_builder.build(history)` → `list[LLMMessage]`;
   - `summarizer.summarize(messages, target_tokens=2000)` → `LLMMessage(content="...")`;
   - извлечение `content` (str | list[ContentPart] | None);
   - `token_counter.count_messages([summary])` → `summary_tokens`;
   - возврат `SubagentResult(summary, token_count, source_scope)`.
4. `process_subagent_response(parent="orchestrator", subagent="log-analyzer", response=...)`:
   - `summarizer.summarize(messages, target_tokens=N)` → суммаризация;
   - `SubagentResult(summary="...", token_count=..., source_scope="log-analyzer", shared_items=[])`;
   - родитель получает **только** summary, не сырой контекст.

### Выход

```python
SubagentResult(
    summary="Log-анализ: 3 аномалии в auth/login.py, 1 в auth/validators.py. Подозрение на race condition.",
    token_count=85,
    source_scope="log-analyzer",
    shared_items=[],   # без федерации
)
```

```
context.multiagent.create_child  parent=sess_main child=sess_main_child_log-analyzer
context.multiagent.collect_summary.start  child=sess_main_child_log-analyzer
context.multiagent.collect_summary.complete  child=... summary_length=312
                                                summary_tokens=85 history_messages=12
context.subagent.process.start  parent=orchestrator subagent=log-analyzer
context.subagent.process.complete  parent=orchestrator subagent=log-analyzer
                                  summary_length=312 token_count=85 fallback=False
```

> **Изоляция:** субагент не загрязнил контекст родителя промежуточными ходами.
> Родитель получил только `summary` (85 токенов), а не полный диалог субагента (12 сообщений,
> ~2000 токенов). Экономия ~95%.

**Graceful degradation:** если `summarizer` недоступен или `summarize()` упал,
`process_subagent_response` возвращает усечённый результат с `fallback=True` в логах.

---

## Сводка: вход → преобразования → выход

| Итерация | Вход | Ключевое преобразование | Выход (токены) |
|----------|------|--------------------------|----------------|
| 1 | пустая история + промпт | Слой A: анализ задачи + сбор 2 файлов; гидрация | baseline 3300 + tail 20 |
| 2 | + tool_result | Слой C: **кэш-хит** на повторном файле (0 RPC) | baseline 3300 + tail 1240 |
| 3 | большой файл, длинная история | Слой C: **скелет** session.py (3500→250); `ensure_context_fits`: **Prune** 135k→52k | baseline 52000 |
| 4a | обычный ход | Слой B: `diff`=UNCHANGED → **baseline из эпохи, шлётся только tail** | tail 30 (кэш-хит на 52k) |
| 4b | `fs/write` | **единый сигнал инвалидации** → reconcile UPDATED → новая эпоха `fp_c2` | baseline пересобран 52010 |
| 5 | рефакторинг (Phase 5) | Слой A: **recursive deps** (max_depth=3) + Dart imports | 4 файла вместо 1 (target) |
| 6 | мультиагент (Phase 6) | Слой D: **child session** + ConversationSummarizer → `SubagentResult.summary` (85t) | summary 85t вместо 2000t |

**Что демонстрирует пример:**
- **Слой A** (итер. 1) — агент сам собрал нужные файлы, пользователь не прикладывал контекст вручную.
- **Слой C** (итер. 2–3) — кэш файлов убирает повторные RPC; AST-скелет умещает большой файл в окно.
- **Сжатие** (итер. 3) — длинный диалог влезает в лимит без слепой обрезки.
- **Слой B** (итер. 4) — на длинной сессии переотправляется только дельта (экономия), а правки файлов корректно обновляют baseline через единый сигнал.
- **Слой A — Phase 5** (итер. 5) — recursive dependencies дают транзитивные импорты (глубина 3), Dart-импорты (`import '...'`, `export '...'`) распознаются.
- **Слой D — Phase 6** (итер. 6) — child session изолирует субагента, родитель получает только summary (экономия ~95% токенов).

---

## Связанные документы
- [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md) — слои A–D, жизненный цикл, сжатие
- [STRATEGY_INTEGRATION.md](./STRATEGY_INTEGRATION.md) — как стратегии вызывают `build_context()`
- [DATA_MODELS.md](./DATA_MODELS.md) — `PayloadEnvelope`, `ContextItem`, `ContextEpoch`, `ReconcileResult`
