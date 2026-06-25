# Спецификация возможности Context Multiagent

## ADDED Requirements

### Requirement: ChildSessionManager изолирует субагентов
Система ДОЛЖНА изолировать субагентов в дочерних сессиях по умолчанию.

#### Scenario: Создание дочерней сессии
- **WHEN** вызывается `create_child(parent, subagent_scope)`
- **THEN** система создаёт новый `SessionState` для дочернего элемента с изолированным контекстом, возвращает дочернюю сессию

#### Scenario: Дочерняя сессия имеет отдельную область
- **WHEN** дочерняя сессия создана
- **THEN** дочерний элемент имеет свой собственный `agent_scope`, отдельный от родителя

#### Scenario: Дочерняя сессия имеет отдельную эпоху
- **WHEN** дочерняя сессия выполняется
- **THEN** дочерний элемент имеет свой собственный `ContextEpoch`, отдельный от родителя

### Requirement: process_subagent_response суммаризирует для родителя
Система ДОЛЖНА суммаризировать ответ субагента для родительского агента.

#### Scenario: Успешная суммаризация
- **WHEN** вызывается `process_subagent_response(parent_scope, subagent_scope, response)`
- **THEN** система возвращает `SubagentResult` с `summary` (суммаризированный результат), `token_count`, `source_scope`

#### Scenario: Summary добавляется в контекст родителя
- **WHEN** субагент завершается
- **THEN** `SubagentResult.summary` добавляется в область родителя как `ContextType.AGENT_REPORT` с `priority=7`

#### Scenario: Деградация при сбое суммаризации
- **WHEN** LLM суммаризация завершается сбоем
- **THEN** система возвращает усечённый сырой результат через `bound_content()`, логирует warning `subagent_summary_degraded`

### Requirement: Сбой субагента не ломает родителя
Система ДОЛЖНА обрабатывать сбои субагентов корректно, не ломая родительский процесс.

#### Scenario: Исключение субагента
- **WHEN** субагент вызывает исключение в дочерней сессии
- **THEN** `process_subagent_response()` возвращает `SubagentResult` с summary ошибки, родитель продолжает работу, логирует error `subagent_failed`

#### Scenario: Таймаут субагента
- **WHEN** дочерняя сессия истекает по таймауту
- **THEN** `collect_summary()` отменяет дочернюю задачу, возвращает `SubagentResult` с меткой таймаута, родитель не блокируется, логирует warning `subagent_timeout`

#### Scenario: Сбой создания дочерней сессии
- **WHEN** `create_child()` завершается сбоем
- **THEN** система возвращает `SubagentResult` с ошибкой родителю, не ломает родительскую стратегию, логирует error `child_session_create_failed`

### Requirement: Федерация — кандидат на отказ
Система ДОЛЖНА рассматривать федеративный `share_item()` как кандидата на отказ (ADR-002 §8).

#### Scenario: Федерация отключена по умолчанию
- **WHEN** `agents.context.multiagent.federation=false` (по умолчанию)
- **THEN** система использует только изоляцию, без федеративного обмена

#### Scenario: Федерация включается только с обоснованием
- **WHEN** федерация включается через feature flag
- **THEN** система разрешает `share_item()` между областями, требует обоснование сценария, не покрываемого изоляцией

#### Scenario: Федерация конфликтует со стабильностью эпох
- **WHEN** общий элемент изменяет baseline другого агента
- **THEN** система ломает эпоху для затронутого агента, логирует warning о конфликте федерации

### Requirement: Orchestrated Strategy использует ContextManager
Система ДОЛЖНА интегрировать `OrchestratedStrategy` с методами `ContextManager`.

#### Scenario: Оркестратор строит контекст
- **WHEN** вызывается `OrchestratedStrategy.execute()`
- **THEN** система вызывает `build_context(agent_scope="orchestrator")` для решения о маршрутизации

#### Scenario: Субагент строит контекст
- **WHEN** оркестратор делегирует субагенту
- **THEN** система вызывает `build_context(agent_scope="<subagent>")` для субагента

#### Scenario: Ответ субагента обрабатывается
- **WHEN** субагент возвращает ответ
- **THEN** система вызывает `process_subagent_response(parent="orchestrator", subagent=..., response)`, добавляет summary в область оркестратора

#### Scenario: ensure_context_fits между раундами
- **WHEN** оркестратор готовит следующий раунд делегирования
- **THEN** система вызывает `ensure_context_fits()` для области оркестратора

### Requirement: Choreography Strategy использует ContextManager
Система ДОЛЖНА интегрировать `ChoreographyStrategy` с методами `ContextManager`.

#### Scenario: Каждый участник строит контекст
- **WHEN** `ChoreographyStrategy.execute()` транслирует участникам
- **THEN** система вызывает `build_context(agent_scope="<participant>")` для каждого участника

#### Scenario: Только ответ победителя обрабатывается
- **WHEN** ответы собраны
- **THEN** система вызывает `process_subagent_response()` только для победителя, отбрасывает остальные ответы

#### Scenario: Нет ensure_context_fits для choreography
- **WHEN** choreography завершается
- **THEN** система не вызывает `ensure_context_fits()` (в отличие от orchestrated/hierarchical)

### Requirement: Hierarchical Strategy использует ContextManager
Система ДОЛЖНА интегрировать `HierarchicalStrategy` с методами `ContextManager`.

#### Scenario: Корень строит контекст
- **WHEN** `HierarchicalStrategy.execute()` запускается
- **THEN** система вызывает `build_context(agent_scope="root")`

#### Scenario: Дочерние сессии создаются для делегирования
- **WHEN** корень делегирует дочернему элементу
- **THEN** система вызывает `ChildSessionManager.create_child(parent, subagent_scope)`, дочерний элемент имеет свою область и эпоху

#### Scenario: Обработка ответа снизу вверх
- **WHEN** дочерний элемент завершается
- **THEN** система вызывает `ChildSessionManager.collect_summary(child)`, затем `process_subagent_response()`, summary идёт родителю

#### Scenario: ensure_context_fits на каждом уровне
- **WHEN** иерархия имеет несколько уровней
- **THEN** система вызывает `ensure_context_fits()` на каждом уровне для предотвращения роста контекста

### Requirement: Интеграция стратегии прозрачна
Система ДОЛЖНА делать модель жизненного цикла (hydration vs epoch) прозрачной для стратегий.

#### Scenario: Стратегия не знает о жизненном цикле
- **WHEN** стратегия вызывает `build_context()`
- **THEN** стратегия получает `PayloadEnvelope`, не знает, используется hydration или epoch

#### Scenario: Переключение жизненного цикла не требует изменений стратегии
- **WHEN** флаг `agents.context.lifecycle.incremental` изменяется
- **THEN** стратегии продолжают работать без модификаций

### Requirement: Метрики мультиагента эмитируются
Система ДОЛЖНА эмитировать метрики для мультиагентных операций.

#### Scenario: Счётчик ответов субагентов
- **WHEN** вызывается `process_subagent_response()`
- **THEN** система инкрементирует счётчик `context_subagent_responses_total` с label `parent_scope`

#### Scenario: Метрика сбоев субагентов
- **WHEN** субагент завершается сбоем
- **THEN** система инкрементирует метрику `context.subagent.failures` с `subagent_scope` и `error_type`

#### Scenario: Метрика таймаутов субагентов
- **WHEN** субагент истекает по таймауту
- **THEN** система инкрементирует метрику `context.subagent.timeouts` с `subagent_scope` и `timeout_sec`
