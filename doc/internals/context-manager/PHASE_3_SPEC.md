# Phase 3 — Источники + сжатие (спецификация для разработки)

> **Статус:** Готово к разработке после Phase 0/1/2 — [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md)
> **Длительность:** 1 неделя
> **Цель:** ввести Registry-pattern для источников контекста (`ContextRegistry`/`ContextSource`), отрендерить каталог скиллов как источник (`SkillContextSource`), собрать единый **3-фазный** `ContextCompactor` (Prune → Skeletonize → Summarize) с `ConversationSummarizer` и корректной деградацией без LLM.

Phase 3 опирается на замороженные в Phase 0 интерфейсы и переиспользует слой C из Phase 2
(`CodeSkeletonizer`, `TokenCounter`). Детект изменений источников вводится здесь **через
fingerprint** (`ContextSource.fingerprint()`), но полная инкрементальная реконсиляция эпох —
Phase 4. Опирается на [INTERFACES.md](./INTERFACES.md), [DATA_MODELS.md](./DATA_MODELS.md)
и [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md) (§3 слой A, §7 сжатие).

---

## Задачи

### T3.1 — `ContextRegistry` / `ContextSource` (Registry pattern)
- Реализовать конкретный реестр под ABC `ContextRegistry` ([INTERFACES.md §2](./INTERFACES.md)): `register()`, `render_baseline()`, `render_updates()`, `detect_changes()`.
- `ContextSource` (ABC §2): свойство `source_id`, `render()`, `fingerprint()` — Codec-отпечаток, **не таймстемп**.
- `render_baseline()` — рендер всех источников один раз на старте эпохи; `render_updates(changes)` — только переданные `source_id`.
- `detect_changes()` — сравнить текущие `fingerprint()` каждого источника с последним снимком, вернуть список изменившихся `source_id`.
- **Acceptance:** регистрация источника работает; `render_baseline()` собирает все источники; после изменения содержимого `detect_changes()` возвращает только затронутый `source_id`; `render_updates()` рендерит ровно его.

### T3.2 — `SkillContextSource` (каталог скиллов)
- Реализовать `ContextSource`, отдающий каталог доступных скиллов из `SkillRegistry` в системный промпт (слой A, [CONSOLIDATED_ARCHITECTURE.md §3](./CONSOLIDATED_ARCHITECTURE.md)).
- `source_id = "skill_catalog"`; `render()` формирует текстовый каталог; `fingerprint()` — детерминированный хэш набора скиллов (имя + версия/сигнатура), отслеживающий добавление/удаление/изменение скиллов.
- Рендер маппится на `ContextItem` с `type=ContextType.SKILL_CATALOG` ([DATA_MODELS.md §3](./DATA_MODELS.md)); приоритет — как у системных правил (не вытесняется при сжатии).
- Источник регистрируется в `ContextRegistry` при сборке `build_context()`.
- **Acceptance:** каталог скиллов попадает в baseline через реестр как отдельный источник; добавление/удаление скилла меняет `fingerprint()` → `detect_changes()` сигналит изменение `skill_catalog`.

### T3.3 — `ConversationSummarizer` (LLM-суммаризация)
- Реализовать ABC `ConversationSummarizer.summarize(messages, *, target_tokens) -> LLMMessage` ([INTERFACES.md §3](./INTERFACES.md)).
- Промпт сохраняет **ключевые решения и состояние задачи**, укладывается в `target_tokens` (контроль через `TokenCounter` из Phase 2).
- Возвращает один `LLMMessage` (сводка), заменяющий суммаризованный диапазон истории.
- **Acceptance:** для длинного диалога возвращается сводка ≤ `target_tokens`, в которой сохранены ключевые решения; результат — валидный `LLMMessage`.

### T3.4 — Единый 3-фазный `ContextCompactor`
- Реализовать ABC `ContextCompactor.compact_if_needed()` ([INTERFACES.md §4](./INTERFACES.md)) как последовательность 3 фаз ([CONSOLIDATED_ARCHITECTURE.md §7](./CONSOLIDATED_ARCHITECTURE.md)):
  1. **Prune** — FIFO-удаление старых tool-выводов (сохраняются первые 2 и последние N сообщений).
  2. **Skeletonize** — AST-сжатие кода через `CodeSkeletonizer` (слой C, Phase 2): тела функций → `...`, сигнатуры сохранены.
  3. **Summarize** — `ConversationSummarizer` (T3.3), если Prune+Skeletonize недостаточно.
- Триггер — превышение `max_context_tokens - reserved_tokens`; между фазами пересчёт токенов через `TokenCounter`, остановка как только payload помещается.
- Сигнатура `compact_if_needed()` совместима с legacy для бесшовной миграции под флагом.
- **Acceptance:** при превышении лимита компактор последовательно проходит Prune → Skeletonize → Summarize и завершает на первой достаточной фазе; результат помещается в окно.

### T3.5 — Деградация без LLM
- При недоступности LLM `ConversationSummarizer` не вызывается; компактор ограничивается **Prune + Skeletonize** (детерминированные фазы).
- Управляется явно (наличие LLM-адаптера / флаг), без исключений в горячем пути.
- **Acceptance:** при отсутствии LLM `compact_if_needed()` отрабатывает только Prune+Skeletonize, не падает; если без Summarize payload не вмещается — фиксируется деградация (лог/метрика), а не краш.

### T3.6 — Интеграция `ContextCompactor` в `ContextManager.ensure_context_fits()`
- Реализовать метод `ContextManager.ensure_context_fits()` (ABC заморожен в Phase 0, [INTERFACES.md §1](./INTERFACES.md)): при превышении `max_context_tokens - reserved_tokens` вызывает `ContextCompactor.compact_if_needed()` над `envelope.to_messages()` и возвращает новый `PayloadEnvelope`.
- Подключить вызов из `ExecutionEngine` для стратегий Single/Hierarchical (см. [STRATEGY_INTEGRATION.md](./STRATEGY_INTEGRATION.md)).
- **Acceptance:** `ensure_context_fits()` возвращает `PayloadEnvelope`, помещающийся в окно (или логирует деградацию); сборка по-прежнему отдаёт только `PayloadEnvelope`, плоский список не «протекает».

---

## Definition of Done для Phase 3

- [ ] `ContextRegistry`/`ContextSource` реализованы; `render_baseline`/`render_updates`/`detect_changes` покрыты тестами (включая fingerprint-детект).
- [ ] `SkillContextSource` рендерит каталог скиллов как источник; изменение набора скиллов отражается в `fingerprint()`.
- [ ] `ConversationSummarizer` сохраняет ключевые решения и укладывается в `target_tokens`.
- [ ] Единый `ContextCompactor` проходит все 3 фазы (Prune → Skeletonize → Summarize) и останавливается на достаточной.
- [ ] Деградация без LLM (Prune+Skeletonize) работает без регрессий.
- [ ] `ContextManager.ensure_context_fits()` интегрирована с `ContextCompactor`; сжатие вызывается при превышении лимита (T3.6).
- [ ] Типизация проходит; реализации соответствуют замороженным сигнатурам Phase 0.

---

## Что Phase 3 НЕ делает (важно)

- Не реализует **полную инкрементальную реконсиляцию эпох** (`ContextEpoch`/`ContextSnapshot`/`ContextReconciler`) — это Phase 4. Здесь только детект изменений источников **через `fingerprint()`**, без применения дельт на границах хода.
- Не вводит provider/KV prefix-cache — Phase 4. (Единый сигнал инвалидации файла вводится в Phase 2, T2.4; Phase 4 лишь подписывает на него snapshot-детект.)
- Не реализует `CodeSkeletonizer`/`TokenCounter`/`FileContentCache` — они приходят из Phase 2 и **переиспользуются**.
- Не трогает мультиагентный обмен (`process_subagent_response`/`ChildSessionManager`) — Phase 6.
- Не меняет поведение при `enabled=false` (работает legacy-компактор).

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| `fingerprint()` источника завязан на таймстемп → ложные изменения и рассинхрон baseline | Code-review правило: fingerprint — детерминированный Codec-хэш содержимого/набора, не время; тест на стабильность при неизменном входе |
| Фаза Summarize вызывает LLM в горячем пути → латентность/стоимость на каждом сжатии | Summarize только если Prune+Skeletonize недостаточно; останов на первой достаточной фазе; деградация без LLM как штатный путь |
| `ConversationSummarizer` теряет ключевые решения → деградация качества | Промпт явно требует сохранить решения/состояние задачи; acceptance-тест проверяет наличие ключевых решений в сводке |
| Недетерминизм Skeletonize рвёт стабильность baseline (стык с Phase 4) | Переиспользуется детерминированный `CodeSkeletonizer` из Phase 2 (требование §6/§7); регресс-тест «один вход → один выход» |
| Каталог скиллов вытесняется при сжатии | `SkillContextSource` маппится на `SKILL_CATALOG` с приоритетом системных правил (не вытесняется) |
