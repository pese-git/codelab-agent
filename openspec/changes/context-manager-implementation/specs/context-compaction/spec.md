# Спецификация возможности Context Compaction

## ADDED Requirements

### Requirement: ContextCompactor выполняет три фазы
Система ДОЛЖНА выполнять компактирование в три фазы: Prune → Skeletonize → Summarize.

#### Scenario: Трёхфазное компактирование
- **WHEN** вызывается `compact_if_needed()` и `token_count > max_context_tokens - reserved_tokens`
- **THEN** система запускает Prune (FIFO удаление), затем Skeletonize (AST сжатие), затем Summarize (LLM суммаризация)

#### Scenario: Порядок фаз фиксирован
- **WHEN** компактирование инициировано
- **THEN** Prune запускается первым, Skeletonize вторым, Summarize третьим

#### Scenario: Сигнатура компактирования совместима с legacy
- **WHEN** вызывается `compact_if_needed(messages, max_context_tokens, reserved_tokens)`
- **THEN** сигнатура соответствует legacy `ContextCompactor.compact_if_needed()` для бесшовной миграции

### Requirement: Фаза Prune удаляет старые tool outputs
Система ДОЛЖНА удалять старые сообщения tool outputs используя FIFO, сохраняя первые 2 и последние N сообщений.

#### Scenario: Prune сохраняет первые и последние сообщения
- **WHEN** Prune инициируется на истории из 200 сообщений
- **THEN** система сохраняет первые 2 сообщения и последние N сообщений, удаляет средние tool outputs

#### Scenario: Prune удаляет пары tool_call + tool_result
- **WHEN** Prune удаляет tool result
- **THEN** система удаляет соответствующий tool_call для поддержания валидности протокола

#### Scenario: Prune не создаёт осиротевших сообщений
- **WHEN** Prune завершается
- **THEN** каждый `tool_result` имеет соответствующий `tool_call`, нет осиротевших сообщений

### Requirement: Фаза Skeletonize сжимает код
Система ДОЛЖНА сжимать файлы кода используя `CodeSkeletonizer` во время компактирования.

#### Scenario: Skeletonize сжимает read-only файлы
- **WHEN** запускается фаза Skeletonize
- **THEN** система применяет `skeletonize()` к большим файлам кода, которые не редактируются агентом

#### Scenario: Skeletonize пропускает неподдерживаемые языки
- **WHEN** файл не на Python или неподдерживаемый язык
- **THEN** система пропускает skeletonization для этого файла, использует оригинальное содержимое

#### Scenario: Skeletonize обеспечивает экономию токенов
- **WHEN** skeleton произведён
- **THEN** skeleton на 80-85% меньше оригинала (для Python файлов)

### Requirement: Фаза Summarize использует LLM
Система ДОЛЖНА суммаризировать разговор используя LLM, когда Prune + Skeletonize недостаточны.

#### Scenario: Summarize инициируется при необходимости
- **WHEN** Prune + Skeletonize не снижают ниже лимита
- **THEN** система вызывает `ConversationSummarizer.summarize(messages, target_tokens)`

#### Scenario: Summarize сохраняет ключевые решения
- **WHEN** суммаризация завершается
- **THEN** summary содержит ключевые решения, состояние задачи, важный контекст

#### Scenario: Summarize при недоступности LLM
- **WHEN** LLM провайдер недоступен
- **THEN** система пропускает фазу Summarize, продолжает только с Prune + Skeletonize, логирует warning `summarization_failed_degrade_to_prune`

### Requirement: Компактирование учитывает приоритет
Система ДОЛЖНА не вытеснять элементы с `priority >= 10` во время компактирования.

#### Scenario: Системные правила не вытесняются
- **WHEN** компактирование нуждается в снижении токенов
- **THEN** система не вытесняет `system_rules` (priority=10)

#### Scenario: Промпт пользователя не вытесняется
- **WHEN** компактирование нуждается в снижении токенов
- **THEN** система не вытесняет `user_prompt` (priority=8), если нет критического переполнения

#### Scenario: Порядок eviction по приоритету
- **WHEN** элементы вытесняются
- **THEN** система вытесняет сначала наименьший приоритет: `file_skeleton=3` → `terminal_output=4` → `file_content=5` → ... → `system_rules=10`

### Requirement: Жёсткое усечение после трёх фаз
Система ДОЛЖНА выполнять жёсткое усечение, если payload всё ещё превышает бюджет после трёх фаз.

#### Scenario: Жёсткое усечение по приоритету
- **WHEN** `token_count > max_context_tokens - reserved_tokens` после Prune + Skeletonize + Summarize
- **THEN** система выполняет жёсткое усечение через `TokenBudgetManager.bound_content()` по приоритету, вытесняет от наименьшего приоритета вверх

#### Scenario: Критические элементы превышают бюджет
- **WHEN** сами `system_rules` (priority >= 10) превышают бюджет
- **THEN** система усекает критические элементы как последнюю меру, логирует error `critical_items_exceed_budget`, не вызывает исключение в горячем пути

#### Scenario: Переполнение провайдера с приблизительным счётчиком
- **WHEN** `ApproximateTokenCounter` недооценивает и провайдер отклоняет
- **THEN** система повторяет `ensure_context_fits()` с более строгим лимитом, логирует warning `budget_underestimated_retry`

### Requirement: Осиротевшие tool сообщения санитизируются
Система ДОЛЖНА санитизировать осиротевшие tool сообщения перед формированием `PayloadEnvelope`.

#### Scenario: Осиротевший tool_result удаляется
- **WHEN** `tool_result` не имеет соответствующего `tool_call` в payload
- **THEN** система удаляет осиротевший `tool_result` или конвертирует в нейтральное текстовое сообщение, логирует `orphaned_tool_result_dropped`

#### Scenario: Осиротевший tool_call дополняется
- **WHEN** `tool_call` не имеет соответствующего `tool_result`
- **THEN** система добавляет placeholder result или удаляет `tool_call` для поддержания валидности протокола

#### Scenario: Prune удаляет пары
- **WHEN** Prune удаляет tool сообщения
- **THEN** система удаляет `tool_call` + `tool_result` вместе, не создаёт сирот

### Requirement: Метрики компактирования эмитируются
Система ДОЛЖНА эмитировать метрики для коэффициента компактирования, длительности и деградации.

#### Scenario: Метрика коэффициента компактирования
- **WHEN** компактирование завершается
- **THEN** система эмитирует histogram `context_compaction_ratio` с label `phase`

#### Scenario: Метрика количества компактирований
- **WHEN** компактирование инициируется
- **THEN** система инкрементирует счётчик `context_compaction_total`

#### Scenario: Метрика деградации
- **WHEN** фаза Summarize пропускается
- **THEN** система инкрементирует счётчик `context_compaction_degraded_total` с label `reason`

### Requirement: ensure_context_fits гарантирует бюджет
Система ДОЛЖНА гарантировать, что payload помещается в `max_context_tokens - reserved_tokens`.

#### Scenario: ensure_context_fits снижает токены
- **WHEN** вызывается `ensure_context_fits(envelope, max_context_tokens, reserved_tokens)`
- **THEN** возвращённый envelope имеет `token_count <= max_context_tokens - reserved_tokens`

#### Scenario: ensure_context_fits сохраняет критические элементы
- **WHEN** необходимо компактирование
- **THEN** элементы с `priority >= 10` сохраняются, если нет критического переполнения

#### Scenario: ensure_context_fits не вызывает исключение в горячем пути
- **WHEN** компактирование завершается сбоем или бюджет не может быть достигнут
- **THEN** система деградирует корректно (жёсткое усечение, логирование), не вызывает исключение
