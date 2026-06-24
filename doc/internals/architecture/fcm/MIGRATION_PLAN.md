# FCM Migration Plan

> **Версия:** 1.0  
> **Дата:** 24 июня 2026  
> **Для кого:** Разработчики, имплементирующие FCM

---

## Оглавление

1. [Current State Analysis](#1-current-state-analysis)
2. [Breaking Changes](#2-breaking-changes)
3. [Feature Flag Strategy](#3-feature-flag-strategy)
4. [Migration Phases](#4-migration-phases)
5. [Rollback Strategy](#5-rollback-strategy)
6. [Monitoring Checklist](#6-monitoring-checklist)
7. [Testing Requirements](#7-testing-requirements)

---

## 1. Current State Analysis

### 1.1. Existing ContextCompactor

**Расположение:** `src/codelab/server/agent/context_compactor.py`

**Текущая реализация:**
```python
class ContextCompactor:
    def __init__(
        self,
        llm: LLMProvider | None = None,
        model: str = "openai/gpt-4o-mini",
        max_context_tokens: int = 128000,
        reserved_tokens: int = 4096,
    ) -> None: ...
    
    async def compact_if_needed(
        self,
        history: list[LLMMessage],
    ) -> tuple[list[LLMMessage], bool, str]:
        """Двухфазное сжатие: Prune → Summarize."""
```

**Что есть:**
- ✅ Фаза 1: Prune (FIFO удаление tool results)
- ✅ Фаза 2: Summarize (LLM-суммаризация)
- ✅ Guards (история <= 5 → no compaction)

**Что отсутствует:**
- ❌ Фаза Skeletonize (AST-сжатие кода)
- ❌ Точный подсчёт токенов (tiktoken)
- ❌ Приоритизация элементов
- ❌ Изолированные скоупы агентов
- ❌ Кэш содержимого файлов

### 1.2. ExecutionEngine Integration

**Расположение:** `src/codelab/server/agent/execution_engine.py`

**Текущая сигнатура:**
```python
class ExecutionEngine:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        compactor: ContextCompactor | None = None,  # ← текущий параметр
        history_builder: HistoryBuilder | None = None,
        tool_filter: ToolFilter | None = None,
        sanitizer: MessageSanitizer | None = None,
        plan_extractor: PlanExtractor | None = None,
    ) -> None: ...
    
    async def build_context(
        self,
        session: SessionState,
        prompt: str,
        system_prompt: str | None = None,
        mcp_manager: Any | None = None,
        content_parts: list[Any] | None = None,
        # ❌ Отсутствует: agent_scope: str = "single"
    ) -> AgentContext: ...
```

### 1.3. Dependencies

**Используемые стратегии:**
- `SingleStrategy` (src/codelab/server/agent/strategies/)
- Другие стратегии пока не существуют (multi-agent в планах)

**Тесты:**
- `tests/server/agent/test_context_compactor.py` (100% coverage)

---

## 2. Breaking Changes

### 2.1. API Changes

| Component | Current API | New API | Breaking? | Mitigation |
|-----------|-------------|---------|-----------|------------|
| **ExecutionEngine.__init__** | `compactor: ContextCompactor \| None` | `context_manager: ContextManager \| None` + `compactor` (deprecated) | ⚠️ Partial | Feature flag + backward compat |
| **ExecutionEngine.build_context** | 5 параметров | +1 parameter: `agent_scope: str = "single"` | ❌ No | Default value |
| **ContextCompactor** location | `agent/context_compactor.py` | `agent/context/compactor.py` | ✅ Yes | Keep old location for now |

### 2.2. New Components (не breaking changes)

Новые компоненты не ломают существующий код:

```
src/codelab/server/agent/context/     (NEW directory)
├── __init__.py
├── token_counter.py                   (NEW)
├── ast_skeletonizer.py                (NEW)
├── file_cache.py                      (NEW)
├── compactor.py                       (NEW, refactored)
├── items.py                           (NEW)
├── scope.py                           (NEW)
├── manager.py                         (NEW)
└── cache.py                           (NEW)

src/codelab/server/tools/executors/decorators/
└── cache_invalidation.py              (NEW)
```

### 2.3. Backward Compatibility Strategy

**Principle:** Существующий код продолжает работать без изменений

**Implementation:**
```python
class ExecutionEngine:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        # NEW: accept both (transitional period)
        compactor: ContextCompactor | None = None,
        context_manager: ContextManager | None = None,
        ...,
    ) -> None:
        self.tool_registry = tool_registry
        
        # Backward compatibility: если оба None, создаём legacy compactor
        if compactor is None and context_manager is None:
            from codelab.server.agent.context_compactor import ContextCompactor
            compactor = ContextCompactor()
        
        self.compactor = compactor
        self.context_manager = context_manager
        
        # Log deprecation warning
        if compactor is not None and context_manager is None:
            logger.warning(
                "compactor parameter is deprecated, use context_manager instead",
                deprecation_version="v2.3",
                removal_version="v3.0",
            )
    
    async def build_context(
        self,
        session: SessionState,
        prompt: str,
        system_prompt: str | None = None,
        mcp_manager: Any | None = None,
        content_parts: list[Any] | None = None,
        agent_scope: str = "single",  # NEW: default value для backward compat
    ) -> AgentContext:
        # ... history building ...
        
        # Feature flag logic
        if self.context_manager is not None:
            # NEW path: FCM
            history = await self._build_via_fcm(
                session, system_prompt, agent_scope
            )
        elif self.compactor is not None:
            # LEGACY path: ContextCompactor
            history, _, _ = await self.compactor.compact_if_needed(history)
        
        return AgentContext(...)
```

---

## 3. Feature Flag Strategy

### 3.1. Configuration Schema

**Файл:** `config.toml`

```toml
[agents.context]
# Master switch для FCM
enable_fcm = false  # default: legacy ContextCompactor

# Sub-features (require enable_fcm=true)
use_tiktoken = true             # точный подсчёт токенов
enable_ast_skeletonization = true  # AST-сжатие
enable_file_cache = true        # кэш содержимого файлов

# Performance tuning
[agents.context.cache]
max_size = 1000  # LRU cache size

[agents.context.compaction]
max_context_tokens = 128000
reserved_tokens = 4096
```

### 3.2. Environment Variable Override

Для testing/staging без изменения config.toml:

```bash
# Override master switch
export CODELAB_FCM_ENABLED=true

# Override sub-features
export CODELAB_FCM_AST_SKELETONIZATION=false
```

### 3.3. Feature Flag Hierarchy

```
enable_fcm (Master)
├─ false → Legacy ContextCompactor (current behavior)
│
└─ true  → FederatedContextManager
    ├─ use_tiktoken
    │  ├─ true  → TiktokenCounter (accurate)
    │  └─ false → ApproximateTokenCounter (fallback)
    │
    ├─ enable_ast_skeletonization
    │  ├─ true  → AST-сжатие включено
    │  └─ false → только Prune + Summarize (как legacy)
    │
    └─ enable_file_cache
       ├─ true  → FileContentCache активен
       └─ false → нет кэширования (всегда RPC)
```

### 3.4. Dynamic Rollout (Canary)

**Gradual rollout по session_id:**

```python
import hashlib

def is_fcm_enabled_for_session(
    session_id: str,
    config_enabled: bool,
    rollout_percent: int,
) -> bool:
    """Canary deployment: включаем FCM для % сессий."""
    if not config_enabled:
        return False
    
    # Consistent hashing: одна сессия всегда в одной группе
    hash_val = int(hashlib.md5(session_id.encode()).hexdigest(), 16)
    return (hash_val % 100) < rollout_percent

# Usage в factory/DI container
fcm_enabled = is_fcm_enabled_for_session(
    session_id,
    config.agents.context.enable_fcm,
    rollout_percent=5,  # start with 5%
)
```

---

## 4. Migration Phases

### Phase 0: Preparation (Week 1)

**Цель:** Подготовить инфраструктуру для миграции

**Задачи:**
- [ ] Добавить feature flag infrastructure в Config
- [ ] Обновить ExecutionEngine для приёма обоих параметров (compactor + context_manager)
- [ ] Добавить `agent_scope` parameter в `build_context()` с default value
- [ ] Написать unit tests для backward compatibility
- [ ] Добавить deprecation warnings для старого API
- [ ] Обновить factory/DI для создания compactor vs context_manager

**Acceptance Criteria:**
- Все существующие тесты проходят ✅
- Новый parameter `agent_scope` не ломает existing code ✅
- Feature flag `enable_fcm=false` работает идентично текущему поведению ✅

**Code Changes:**
```python
# src/codelab/server/agent/execution_engine.py
class ExecutionEngine:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        compactor: ContextCompactor | None = None,      # deprecated
        context_manager: ContextManager | None = None,  # NEW
        ...,
    ) -> None:
        # Validation
        if compactor is not None and context_manager is not None:
            raise ValueError("Cannot use both compactor and context_manager")
        
        self.compactor = compactor
        self.context_manager = context_manager
    
    async def build_context(
        self,
        session: SessionState,
        prompt: str,
        system_prompt: str | None = None,
        mcp_manager: Any | None = None,
        content_parts: list[Any] | None = None,
        agent_scope: str = "single",  # NEW
    ) -> AgentContext:
        # Build history
        history = self.history_builder.build(session.history, system_prompt=system_prompt)
        history = self.sanitizer.sanitize(history)
        
        # Branch on feature flag
        if self.context_manager is not None:
            # FCM path (NEW)
            history = await self._build_via_fcm(session, system_prompt, agent_scope)
        else:
            # Legacy path
            if self.compactor is not None:
                history, _, _ = await self.compactor.compact_if_needed(history)
        
        return AgentContext(...)
    
    async def _build_via_fcm(
        self,
        session: SessionState,
        system_prompt: str | None,
        agent_scope: str,
    ) -> list[LLMMessage]:
        """Build context через FCM."""
        # Stub для Phase 0 — реализация в Phase 3-4
        raise NotImplementedError("FCM not implemented yet")
```

### Phase 1: Слой 1 — Утилиты (Week 2-3)

**Цель:** Реализовать foundation компоненты (без изменения ExecutionEngine)

**Задачи:**
- [ ] Реализовать `TokenCounter` (ABC + TiktokenCounter + ApproximateTokenCounter)
- [ ] Реализовать `create_token_counter()` factory function
- [ ] Реализовать `CodeSkeletonizer` (ABC + PythonASTSkeletonizer)
- [ ] Реализовать `FileContentCache` (ABC + InMemoryFileCache)
- [ ] Реализовать `SessionFileCacheRegistry`
- [ ] Реализовать `CacheInvalidationDecorator`
- [ ] 100% test coverage для всех компонентов
- [ ] Benchmark: `PythonASTSkeletonizer` performance (см. PERFORMANCE_REQUIREMENTS.md)

**Acceptance Criteria:**
- Unit tests: 100% coverage ✅
- `TokenCounter` accuracy: tiktoken vs approximate delta < 30% ✅
- `PythonASTSkeletonizer`: p95 latency < 200ms для файлов < 1000 LOC ✅
- `FileContentCache`: LRU eviction работает корректно ✅

**Deliverables:**
```
src/codelab/server/agent/context/
├── __init__.py
├── token_counter.py
├── ast_skeletonizer.py
├── file_cache.py

tests/server/agent/context/
├── test_token_counter.py
├── test_ast_skeletonizer.py
├── test_file_cache.py
```

### Phase 2: Слой 2 — Сжатие (Week 3-4)

**Цель:** Расширить ContextCompactor с AST-скелетированием

**Задачи:**
- [ ] Создать новый `DefaultContextCompactor` в `agent/context/compactor.py`
- [ ] Добавить фазу Skeletonize между Prune и Summarize
- [ ] Интеграция с `TokenCounter` и `CodeSkeletonizer`
- [ ] Перенести логику из старого `context_compactor.py` (рефакторинг)
- [ ] Unit tests для новой фазы Skeletonize
- [ ] Integration tests: ExecutionEngine с `DefaultContextCompactor`

**Acceptance Criteria:**
- Все три фазы работают: Prune → Skeletonize → Summarize ✅
- Backward compatibility: без AST флага поведение идентично legacy ✅
- E2E test: SingleStrategy с новым compactor проходит ✅

**Code Example:**
```python
# src/codelab/server/agent/context/compactor.py
from abc import ABC, abstractmethod

class ContextCompactor(ABC):
    """ABC для сжатия контекста."""
    
    @abstractmethod
    async def compact_if_needed(
        self,
        history: list[LLMMessage],
    ) -> tuple[list[LLMMessage], bool, str]:
        """Сжать если превышает лимит."""
        ...

class DefaultContextCompactor(ContextCompactor):
    """Трёхфазное сжатие: Prune → Skeletonize → Summarize."""
    
    def __init__(
        self,
        token_counter: TokenCounter,
        skeletonizer: CodeSkeletonizer | None = None,
        llm: LLMProvider | None = None,
        enable_skeletonization: bool = True,
        ...,
    ) -> None:
        self.token_counter = token_counter
        self.skeletonizer = skeletonizer
        self.llm = llm
        self.enable_skeletonization = enable_skeletonization
    
    async def compact_if_needed(self, history):
        # Phase 1: Prune
        pruned = self._prune_old_tool_outputs(history)
        if self._within_limit(pruned):
            return pruned, True, "pruned"
        
        # Phase 2: Skeletonize (NEW)
        if self.enable_skeletonization and self.skeletonizer:
            skeletonized = await self._skeletonize_file_content(pruned)
            if self._within_limit(skeletonized):
                return skeletonized, True, "skeletonized"
        
        # Phase 3: Summarize
        if self.llm:
            summarized = await self._summarize_conversation(pruned)
            return summarized, True, "summarized"
        
        return pruned, True, "pruned_only"
    
    async def _skeletonize_file_content(self, history):
        """AST-сжатие для file_content сообщений."""
        result = []
        for msg in history:
            if self._is_file_content(msg):
                skeleton = self.skeletonizer.skeletonize(
                    msg.content, file_id="unknown"
                )
                result.append(LLMMessage(role=msg.role, content=skeleton))
            else:
                result.append(msg)
        return result
```

### Phase 3: Слой 3 — Оркестрация (Week 4-5)

**Цель:** Реализовать FederatedContextManager + интеграция

**Задачи:**
- [ ] Реализовать `ContextItem` (frozen dataclass)
- [ ] Реализовать `AgentContextScope`
- [ ] Реализовать `ContextManager` (ABC)
- [ ] Реализовать `FederatedContextManager`
- [ ] Реализовать `hydrate_from_history()`
- [ ] Реализовать `optimize_and_build_payload()`
- [ ] Интеграция с ExecutionEngine: `_build_via_fcm()`
- [ ] Unit tests для FCM
- [ ] Integration tests: SingleStrategy с FCM

**Acceptance Criteria:**
- `hydrate_from_history()` корректно загружает историю ✅
- `optimize_and_build_payload()` применяет приоритеты ✅
- SingleStrategy с FCM работает идентично legacy (при отключенных фичах) ✅
- Feature flag `enable_fcm=true` корректно переключает на FCM ✅

**Integration Example:**
```python
# src/codelab/server/agent/execution_engine.py
async def _build_via_fcm(
    self,
    session: SessionState,
    system_prompt: str | None,
    agent_scope: str,
) -> list[LLMMessage]:
    """Build context через FCM."""
    scope = self.context_manager.scopes.get(agent_scope)
    
    if scope is None:
        # Скоуп не существует → гидратировать из истории (SingleStrategy)
        await self.context_manager.hydrate_from_history(
            scope_name=agent_scope,
            history=session.history,
            system_prompt=system_prompt,
        )
    
    # Формируем payload
    return await self.context_manager.optimize_and_build_payload(agent_scope)
```

### Phase 4: Feature Flag Rollout (Week 5-6)

**Цель:** Постепенный rollout в production с мониторингом

**Week 5: Internal Testing + Canary**
- [ ] Day 1-2: Internal testing (enable_fcm=true для dev/staging)
- [ ] Day 3: Metrics dashboard setup (latency, memory, errors)
- [ ] Day 4: Canary deployment (5% production traffic)
- [ ] Day 5-7: Monitor + adjust (если нет проблем → увеличить до 10%)

**Week 6: Gradual Rollout**
- [ ] Day 1-2: 25% traffic
- [ ] Day 3-4: 50% traffic
- [ ] Day 5-7: 100% traffic (если всё стабильно)

**Rollout Decision Tree:**
```
Start Canary (5%)
    ↓
Monitor 48h
    ↓
Issues found? ──Yes──> Rollback + Fix ──> Restart Canary
    │
    No
    ↓
Increase to 25%
    ↓
Monitor 48h
    ↓
Issues? ──Yes──> Rollback to 5% + Debug
    │
    No
    ↓
Increase to 50%
    ↓
Monitor 48h
    ↓
Issues? ──Yes──> Rollback to 25% + Fix
    │
    No
    ↓
Deploy 100%
```

**Monitoring Metrics (см. PERFORMANCE_REQUIREMENTS.md):**
- Latency: p50, p95, p99 для `build_context()`
- Memory: per-session memory usage
- Errors: AST parsing failures, token counting errors
- Coverage: % sessions with FCM enabled

### Phase 5: Cleanup (Week 7-8)

**Цель:** Удалить legacy код после успешного rollout

**Задачи:**
- [ ] Удалить старый `context_compactor.py`
- [ ] Удалить `compactor` parameter из ExecutionEngine
- [ ] Удалить feature flags (enable_fcm всегда true)
- [ ] Обновить конфигурацию (удалить enable_fcm)
- [ ] Обновить документацию (убрать упоминания legacy)
- [ ] Финальная проверка: все тесты проходят

**Breaking Changes (Major Version Bump):**
- ExecutionEngine.__init__ больше не принимает `compactor`
- Минимальная версия повышается до v3.0

---

## 5. Rollback Strategy

### 5.1. Immediate Rollback (< 5 minutes)

**Trigger:** Critical production issue (crash loops, severe latency degradation)

**Actions:**
```bash
# 1. Disable feature flag via environment variable
export CODELAB_FCM_ENABLED=false

# 2. Reload server gracefully (no downtime)
systemctl reload codelab-server

# 3. Verify rollback
curl http://localhost:8080/health
# Expected: "fcm_enabled": false

# 4. Monitor recovery
tail -f /var/log/codelab/server.log | grep "fcm"
```

**Verification:**
- Latency p95 returns to baseline
- Error rate drops to normal
- Memory usage stabilizes

### 5.2. Gradual Rollback (staged)

**Trigger:** Non-critical issues (higher latency, minor errors)

**Actions:**
```python
# Reduce rollout percentage
rollout_percent = 25  # было 50%

# Update in config (or dynamic config service)
config.agents.context.fcm_rollout_percent = 25

# Reload server
systemctl reload codelab-server
```

**Monitor for 24h:** Если проблемы сохраняются → further reduce to 5% или full rollback.

### 5.3. Data Migration Rollback

**Question:** Нужна ли миграция persistent state?

**Answer:** ❌ **НЕТ** — FCM не хранит persistent state

- `FileContentCache` — in-memory, ephemeral per session
- `AgentContextScope` — in-memory, recreated каждый turn
- `session.history` — неизменна (FCM не модифицирует)

**Следствие:** Rollback безопасен в любой момент без data migration.

### 5.4. Rollback Playbook

**Step-by-step инструкция для on-call engineer:**

1. **Identify issue:** Alert в monitoring dashboard
2. **Assess severity:**
   - Critical (crash, p99 > 10s) → Immediate Rollback
   - High (p95 > 2s, errors > 1%) → Gradual Rollback
   - Medium → Monitor, reduce rollout %
3. **Execute rollback:** (см. 5.1 или 5.2)
4. **Verify recovery:** Check metrics, logs
5. **Post-mortem:** File incident report, update EDGE_CASES.md

---

## 6. Monitoring Checklist

### 6.1. Key Metrics

**Latency:**
```python
# p50, p95, p99, max
metrics.timing("fcm.build_context.latency", duration_ms)
metrics.timing("fcm.ast_skeletonize.latency", duration_ms)
metrics.timing("fcm.optimize_and_build_payload.latency", duration_ms)
```

**Memory:**
```python
metrics.gauge("fcm.cache.size_bytes", cache.get_size())
metrics.gauge("fcm.scope.token_count", scope.get_total_tokens())
metrics.gauge("fcm.memory_per_session_mb", memory_mb)
```

**Errors:**
```python
metrics.counter("fcm.errors", tags={"type": "ast_parse_failed"})
metrics.counter("fcm.errors", tags={"type": "token_count_failed"})
metrics.counter("fcm.errors", tags={"type": "cache_invalidation_failed"})
```

**Business Metrics:**
```python
metrics.gauge("fcm.enabled_sessions_percent", enabled_percent)
metrics.histogram("fcm.skeleton_savings_percent", savings)
```

### 6.2. Alerts

```yaml
# alerts.yaml
- alert: FCM_High_Latency_P95
  expr: fcm_build_context_latency_p95 > 500ms
  for: 5m
  severity: warning
  action: Reduce rollout or investigate

- alert: FCM_High_Latency_P99
  expr: fcm_build_context_latency_p99 > 2000ms
  for: 2m
  severity: critical
  action: Immediate rollback

- alert: FCM_Memory_High
  expr: fcm_memory_per_session_mb > 5
  for: 10m
  severity: warning
  action: Check for memory leaks

- alert: FCM_Error_Rate_High
  expr: rate(fcm_errors[5m]) > 0.05  # 5% error rate
  for: 3m
  severity: critical
  action: Rollback + investigate

- alert: FCM_AST_Parse_Failures
  expr: rate(fcm_errors{type="ast_parse_failed"}[5m]) > 0.1
  for: 5m
  severity: warning
  action: Review failing files
```

### 6.3. Dashboard

**Key Panels:**
1. Latency comparison: FCM vs Legacy (side-by-side)
2. Memory usage trend
3. Error rate by type (stacked bars)
4. Rollout percentage (gauge)
5. Skeleton savings (histogram)

---

## 7. Testing Requirements

### 7.1. Unit Tests

**Новые компоненты:**
- [ ] `test_token_counter.py` — 100% coverage
- [ ] `test_ast_skeletonizer.py` — 100% coverage
- [ ] `test_file_cache.py` — 100% coverage
- [ ] `test_compactor.py` — 100% coverage (DefaultContextCompactor)
- [ ] `test_scope.py` — 100% coverage
- [ ] `test_manager.py` — 100% coverage (FederatedContextManager)

**Backward Compatibility:**
- [ ] `test_execution_engine_backward_compat.py`
  - Legacy compactor path работает
  - Новый agent_scope parameter не ломает existing calls
  - Deprecation warnings логируются

### 7.2. Integration Tests

**ExecutionEngine + FCM:**
- [ ] SingleStrategy с enable_fcm=true
- [ ] Hydrate from history работает корректно
- [ ] Compaction срабатывает при превышении лимита
- [ ] AST-skeletonization применяется к file_content

**Feature Flags:**
- [ ] enable_fcm=false → legacy behavior
- [ ] enable_fcm=true, enable_ast_skeletonization=false → no AST
- [ ] enable_fcm=true, use_tiktoken=false → approximate counter

### 7.3. E2E Tests

**Scenarios:**
- [ ] Новая сессия → prompt → FCM гидратирует историю
- [ ] Длинная история → compaction → payload уменьшен
- [ ] Файл > max_tokens → truncation or skeletonization
- [ ] Canary rollout simulation → 5% sessions используют FCM

### 7.4. Performance Tests

**Benchmarks:**
- [ ] build_context() latency: 1000 iterations, measure p50/p95/p99
- [ ] AST skeletonization: 100 файлов (разные размеры), measure latency
- [ ] Memory profiling: 1000 concurrent sessions, measure total memory
- [ ] Load test: 100 req/sec sustained for 5 min, no OOM

**Acceptance:**
- Latency не хуже +50% vs legacy
- Memory не хуже +100% vs legacy
- No memory leaks (stability test 1h)

---

## 8. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Latency regression > 50%** | Medium | High | Feature flag + rollback, performance benchmarks before rollout |
| **Memory leak в FileContentCache** | Low | Critical | Memory profiling, load tests, monitoring alerts |
| **AST parsing crashes на production code** | Medium | Medium | Graceful degradation (fallback to original), extensive testing |
| **Breaking changes break existing integrations** | Low | Critical | Backward compatibility layer, deprecation warnings, phased deprecation |
| **tiktoken not available в production** | Low | Low | Fallback to ApproximateTokenCounter (tested) |
| **Rollback сложен/невозможен** | Very Low | Critical | Feature flag infrastructure, no persistent state, tested rollback procedure |

---

## 9. Success Criteria

**Before Production Rollout:**
- [ ] All unit tests pass (100% coverage для новых компонентов)
- [ ] All integration tests pass
- [ ] Performance benchmarks meet SLOs (см. PERFORMANCE_REQUIREMENTS.md)
- [ ] Feature flags работают корректно (enable/disable без перезапуска)
- [ ] Backward compatibility verified (existing code не ломается)
- [ ] Rollback procedure tested (successful rollback in staging)
- [ ] Documentation complete (ARCHITECTURE, INTEGRATION_GUIDE, README updated)

**After 100% Rollout:**
- [ ] Latency p95 <= baseline + 50%
- [ ] Memory usage <= baseline + 100%
- [ ] Error rate < 0.1%
- [ ] No critical incidents for 1 week
- [ ] Positive feedback from users (optional)

**Final Cleanup (Phase 5):**
- [ ] Legacy ContextCompactor removed
- [ ] Feature flags removed (enable_fcm always true)
- [ ] Documentation updated (no mentions of legacy)
- [ ] Version bumped to v3.0 (breaking changes)

---

## Appendix A: Code Migration Examples

### Before (Legacy)

```python
# Factory/DI container
compactor = ContextCompactor(
    llm=llm_provider,
    model="openai/gpt-4o-mini",
)

engine = ExecutionEngine(
    tool_registry=tool_registry,
    compactor=compactor,
)

# Usage
context = await engine.build_context(session, prompt)
```

### After (FCM)

```python
# Слой 1
token_counter = create_token_counter()
skeletonizer = PythonASTSkeletonizer()
cache_registry = SessionFileCacheRegistry()
file_cache = cache_registry.get_or_create(session_id)

# Слой 2
compactor = DefaultContextCompactor(
    token_counter=token_counter,
    skeletonizer=skeletonizer,
    llm=llm_provider,
    enable_skeletonization=config.agents.context.enable_ast_skeletonization,
)

# Слой 3
context_manager = FederatedContextManager(
    token_counter=token_counter,
    skeletonizer=skeletonizer,
    compactor=compactor,
    file_cache=file_cache,
)

# ExecutionEngine
engine = ExecutionEngine(
    tool_registry=tool_registry,
    context_manager=context_manager,  # NEW
)

# Usage (backward compatible)
context = await engine.build_context(
    session,
    prompt,
    agent_scope="single",  # NEW: optional
)
```

---

## Appendix B: Rollout Timeline (Gantt)

```
Week 1: Phase 0 — Preparation
[============================]

Week 2-3: Phase 1 — Слой 1 Utilities
[========================================]

Week 3-4: Phase 2 — Слой 2 Compaction
      [========================================]

Week 4-5: Phase 3 — Слой 3 Orchestration
            [========================================]

Week 5-6: Phase 4 — Feature Flag Rollout
                  [==========================] (Canary + Gradual)

Week 7-8: Phase 5 — Cleanup
                                    [==============]
```

**Total duration:** 7-8 недель от начала до финального cleanup.

**Критический путь:** Phase 1-3 (implementation) — 4 недели.

**Rollout:** 2 недели (canary + gradual увеличение до 100%).

---

## Связанные документы

- [ERROR_HANDLING.md](./ERROR_HANDLING.md) — стратегия обработки ошибок
- [EDGE_CASES.md](./EDGE_CASES.md) — специфика edge cases
- [FEATURE_FLAGS.md](./FEATURE_FLAGS.md) — детали feature flag системы
- [PERFORMANCE_REQUIREMENTS.md](./PERFORMANCE_REQUIREMENTS.md) — SLOs и benchmarks
- [ARCHITECTURE.md](./ARCHITECTURE.md) — полная архитектура FCM
- [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md) — пошаговое руководство
