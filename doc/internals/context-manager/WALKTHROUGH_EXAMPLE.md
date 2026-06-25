# Context Manager — Пример работы (agent loop, шаг за шагом)

> **Статус:** Канон (иллюстрация) — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Дата:** 25 июня 2026
>
> Сквозной прогон: какие данные подаются на **вход**, какие **преобразования** происходят
> внутри (слои A→B→C), и что получается на **выходе** (`PayloadEnvelope`). Показаны несколько
> итераций agent loop, включая кэш файлов, скелетирование, 3-фазное сжатие и инкрементальную эпоху.
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
    participant L as LLM (LLMAdapter)

    Note over U,L: Итерация 1 — сбор контекста (гидрация)
    U->>CM: prompt «исправь падение при пустом email»
    CM->>CM: TaskAnalyzer → Gatherer (read login.py, validators.py)
    CM->>FC: set(login.py), set(validators.py)
    CM->>L: PayloadEnvelope baseline 3300 + tail 20 (fp_a1)
    L-->>CM: tool_call: read test_login.py

    Note over U,L: Итерация 2 — продолжение (кэш-хит)
    CM->>FC: get(login.py) ✓ кэш-хит (0 RPC)
    CM->>L: baseline 3300 + tail 1240 (fp_a1)
    L-->>CM: правка validators.py; read session.py (большой)

    Note over U,L: Итерация 3 — скелет + 3-фазное сжатие
    CM->>CM: skeletonize(session.py) 3500→250; Prune 135k→52k
    CM->>L: baseline 52000 (fp_b7)
    L-->>CM: fs/write validators.py (фикс)

    Note over U,L: Итерация 4a — инкрементальная эпоха (baseline неизменен)
    CM->>CM: snapshot.diff = UNCHANGED → baseline из эпохи
    CM->>L: только tail 30 (fp_b7 → prompt-cache хит)
    L-->>CM: обычный ход

    Note over U,L: Итерация 4b — правка файла → инвалидация
    L-->>CM: fs/write validators.py
    CM->>FC: invalidate(validators.py) + сигнал изменения
    CM->>CM: reconcile = UPDATED → новая эпоха fp_c2
    CM->>L: baseline пересобран 52010 (fp_c2)
    L-->>U: end_turn → ответ
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

## Сводка: вход → преобразования → выход

| Итерация | Вход | Ключевое преобразование | Выход (токены) |
|----------|------|--------------------------|----------------|
| 1 | пустая история + промпт | Слой A: анализ задачи + сбор 2 файлов; гидрация | baseline 3300 + tail 20 |
| 2 | + tool_result | Слой C: **кэш-хит** на повторном файле (0 RPC) | baseline 3300 + tail 1240 |
| 3 | большой файл, длинная история | Слой C: **скелет** session.py (3500→250); `ensure_context_fits`: **Prune** 135k→52k | baseline 52000 |
| 4a | обычный ход | Слой B: `diff`=UNCHANGED → **baseline из эпохи, шлётся только tail** | tail 30 (кэш-хит на 52k) |
| 4b | `fs/write` | **единый сигнал инвалидации** → reconcile UPDATED → новая эпоха `fp_c2` | baseline пересобран 52010 |

**Что демонстрирует пример:**
- **Слой A** (итер. 1) — агент сам собрал нужные файлы, пользователь не прикладывал контекст вручную.
- **Слой C** (итер. 2–3) — кэш файлов убирает повторные RPC; AST-скелет умещает большой файл в окно.
- **Сжатие** (итер. 3) — длинный диалог влезает в лимит без слепой обрезки.
- **Слой B** (итер. 4) — на длинной сессии переотправляется только дельта (экономия), а правки файлов корректно обновляют baseline через единый сигнал.

---

## Связанные документы
- [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md) — слои A–D, жизненный цикл, сжатие
- [STRATEGY_INTEGRATION.md](./STRATEGY_INTEGRATION.md) — как стратегии вызывают `build_context()`
- [DATA_MODELS.md](./DATA_MODELS.md) — `PayloadEnvelope`, `ContextItem`, `ContextEpoch`, `ReconcileResult`
