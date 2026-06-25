# Спецификация возможности Context Lifecycle

## ADDED Requirements

### Requirement: PayloadEnvelope разделяет Baseline и Tail
Система MUST поддерживать `PayloadEnvelope` с явным разделением иммутабельного `baseline` и дельт `tail`.

#### Scenario: Структура PayloadEnvelope
- **WHEN** вызывается `build_context()`
- **THEN** система возвращает `PayloadEnvelope` с `baseline: list[LLMMessage]`, `tail: list[LLMMessage]`, `baseline_fingerprint: str`, `token_count: int`

#### Scenario: to_messages уплощает baseline и tail
- **WHEN** вызывается `envelope.to_messages()`
- **THEN** система возвращает `[*baseline, *tail]` как плоский `list[LLMMessage]`

#### Scenario: Стабильность fingerprint baseline
- **WHEN** содержимое baseline не изменяется между вызовами
- **THEN** `baseline_fingerprint` остаётся идентичным (детерминированный хеш)

### Requirement: ContextEpoch управляет инкрементальными обновлениями
Система MUST поддерживать `ContextEpoch` с иммутабельным baseline и инкрементальными `mid_conversation_messages`.

#### Scenario: Создание эпохи
- **WHEN** начинается новая эпоха
- **THEN** система создаёт `ContextEpoch` с `epoch_id`, `baseline`, `baseline_fingerprint`, пустыми `mid_conversation_messages`

#### Scenario: get_full_context возвращает baseline + mid_conversation
- **WHEN** вызывается `epoch.get_full_context()`
- **THEN** система возвращает `[*baseline, *mid_conversation_messages]`

#### Scenario: Накопление mid-conversation сообщений
- **WHEN** tool results добавляются во время разговора
- **THEN** система добавляет их в `mid_conversation_messages`, baseline остаётся неизменным

### Requirement: ContextSnapshot обнаруживает изменения через Fingerprint
Система MUST обнаруживать изменения источников используя Codec fingerprints, а не timestamps.

#### Scenario: Создание snapshot
- **WHEN** вызывается `ContextReconciler.snapshot(registry)`
- **THEN** система собирает fingerprints всех источников, возвращает `ContextSnapshot` с `fingerprints: dict[str, str]`

#### Scenario: Diff обнаруживает изменённые источники
- **WHEN** вызывается `snapshot.diff(other)`
- **THEN** система сравнивает fingerprints, возвращает список `source_id` с изменёнными fingerprints

#### Scenario: Fingerprint основан на Codec
- **WHEN** содержимое источника изменяется
- **THEN** fingerprint изменяется (не зависит от timestamp)

### Requirement: ContextReconciler безопасно применяет изменения
Система MUST применять изменения на безопасных границах с состояниями `UNCHANGED`, `UPDATED` или `DEFERRED`.

#### Scenario: Reconcile без изменений
- **WHEN** вызывается `reconcile(epoch, registry)` и ни один источник не изменился
- **THEN** система возвращает `ReconcileResult(state=UNCHANGED, epoch_broken=False)`

#### Scenario: Reconcile с изменением источника на безопасной границе
- **WHEN** источник изменился и reconcile вызывается на безопасной границе
- **THEN** система возвращает `ReconcileResult(state=UPDATED, updated_sources=[...], epoch_broken=True)`, baseline перестраивается

#### Scenario: Reconcile с изменением, обнаруженным в середине хода
- **WHEN** изменение обнаружено, но не на безопасной границе
- **THEN** система возвращает `ReconcileResult(state=DEFERRED)`, изменение применяется на следующей границе

#### Scenario: Reconcile с неопределённым изменением
- **WHEN** fingerprint нечитаем или неоднозначен
- **THEN** система консервативно возвращает `ReconcileResult(state=UPDATED, epoch_broken=True)`, перестраивает baseline

### Requirement: ConversationSummarizer сохраняет ключевые решения
Система MUST суммаризировать историю разговора, сохраняя ключевые решения и состояние задачи.

#### Scenario: Успешная суммаризация
- **WHEN** вызывается `summarize(messages, target_tokens)`
- **THEN** система возвращает суммаризированное `LLMMessage` с сохранёнными ключевыми решениями и состоянием

#### Scenario: Деградация при недоступности LLM
- **WHEN** LLM провайдер недоступен
- **THEN** система пропускает фазу Summarize, продолжает только с Prune + Skeletonize, логирует warning `summarization_failed_degrade_to_prune`

#### Scenario: Пустой или невалидный результат суммаризации
- **WHEN** суммаризатор возвращает пустой или невалидный результат
- **THEN** система обрабатывает это как сбой, деградирует до Prune + Skeletonize

### Requirement: Fingerprint Baseline использует каноническую форму
Система MUST вычислять `baseline_fingerprint` по канонизированному содержимому baseline.

#### Scenario: Канонизация baseline при хешировании
- **WHEN** baseline собирается из источников
- **THEN** система канонизирует содержимое (стабильный порядок, нормализованные пробелы), вычисляет хеш по полному baseline

#### Scenario: Идентичный baseline производит идентичный fingerprint
- **WHEN** одинаковое содержимое поступает в разном порядке
- **THEN** после канонизации fingerprint идентичен

#### Scenario: Различный baseline производит различный fingerprint
- **WHEN** содержимое baseline различается
- **THEN** fingerprint различается (нет коллизий на тестовом корпусе)

### Requirement: Инкрементальная модель экономит токены на стабильном Baseline
Система MUST отправлять только tail, когда baseline не изменён (Фаза 4+).

#### Scenario: Стабильный baseline в инкрементальном режиме
- **WHEN** `incremental=true` и baseline не изменился
- **THEN** система отправляет только `tail` (30 токенов), переиспользует кэшированный baseline (52000 токенов), достигается экономия >60% токенов

#### Scenario: Изменение baseline ломает эпоху
- **WHEN** источник изменяется и `epoch_broken=True`
- **THEN** система перестраивает baseline, отправляет новый baseline + tail, prompt cache промахивается, но корректность сохраняется

### Requirement: Разрывы эпох ограничены
Система MUST ограничивать разрывы эпох не более чем одним за ход.

#### Scenario: Множественные изменения за один ход
- **WHEN** несколько источников изменяются за один ход
- **THEN** система применяет все изменения в одном `epoch_broken=True`, а не множественные разрывы

#### Scenario: Debounce с состоянием DEFERRED
- **WHEN** накапливаются изменения `DEFERRED`
- **THEN** система применяет их вместе на следующей границе, один разрыв эпохи
