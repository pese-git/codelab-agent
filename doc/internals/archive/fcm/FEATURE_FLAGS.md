# FCM Feature Flags & Configuration

> **ARCHIVED.** Этот документ архивирован. Каноническая документация — в [`doc/internals/context-manager/`](../../context-manager/). См. также [ADR-002](../adr/ADR-002-context-manager-consolidation.md).


> **Вер��ия:** 1.0  
> **Дата:** 24 июня 2026

---

## 1. Configuration Schema

### config.toml

```toml
[agents.context]
# Master switch
enable_fcm = false  # default: legacy ContextCompactor

# Sub-features (require enable_fcm=true)
use_tiktoken = true                    # точный подсчёт токенов (fallback: approximate)
enable_ast_skeletonization = true      # AST-сжатие кода
enable_file_cache = true               # кэш содержимого файлов
enable_multi_agent_scopes = false      # изолированные скоупы (for future)

# Cache settings
[agents.context.cache]
max_size = 1000                        # LRU cache size (per session)

# Compaction settings
[agents.context.compaction]
max_context_tokens = 128000            # model context window
reserved_tokens = 4096                 # buffer for response
```

### Environment Variables Override

```bash
# Production override без изменения config file
export CODELAB_FCM_ENABLED=true
export CODELAB_FCM_AST_SKELETONIZATION=false  # gradual rollout

# Canary deployment
export CODELAB_FCM_ROLLOUT_PERCENT=5  # 5% of sessions
```

---

## 2. Feature Flag Hierarchy

```
enable_fcm (Master)
├─ false → Legacy ContextCompactor
│          (current behavior, двухфазное сжатие)
│
└─ true  → FederatedContextManager
    │
    ├─ use_tiktoken
    │  ├─ true  → TiktokenCounter (accurate, recommended)
    │  └─ false → ApproximateTokenCounter (len // 4)
    │
    ├─ enable_ast_skeletonization
    │  ├─ true  → Prune → Skeletonize → Summarize (трёхфазное)
    │  └─ false → Prune → Summarize (как legacy)
    │
    ├─ enable_file_cache
    │  ├─ true  → FileContentCache активен (no RPC duplication)
    │  └─ false → каждое чтение = RPC (legacy behavior)
    │
    └─ enable_multi_agent_scopes (future)
       ├─ true  → изолированные скоупы per agent
       └─ false → single global scope
```

---

## 3. Implementation

### Dependency Injection

```python
# src/codelab/server/agent/factory.py
def create_execution_engine(
    tool_registry: ToolRegistry,
    config: Config,
    llm_provider: LLMProvider,
    session_id: str,
) -> ExecutionEngine:
    """Factory для ExecutionEngine с feature flags."""
    
    # Feature flag check
    fcm_enabled = config.agents.context.enable_fcm
    
    if fcm_enabled:
        # NEW: FederatedContextManager path
        token_counter = create_token_counter() if config.agents.context.use_tiktoken else ApproximateTokenCounter()
        
        skeletonizer = PythonASTSkeletonizer() if config.agents.context.enable_ast_skeletonization else None
        
        file_cache = None
        if config.agents.context.enable_file_cache:
            cache_registry = get_cache_registry()  # singleton
            file_cache = cache_registry.get_or_create(session_id)
        
        compactor = DefaultContextCompactor(
            token_counter=token_counter,
            skeletonizer=skeletonizer,
            llm=llm_provider,
            enable_skeletonization=config.agents.context.enable_ast_skeletonization,
            max_context_tokens=config.agents.context.compaction.max_context_tokens,
            reserved_tokens=config.agents.context.compaction.reserved_tokens,
        )
        
        context_manager = FederatedContextManager(
            token_counter=token_counter,
            skeletonizer=skeletonizer,
            compactor=compactor,
            file_cache=file_cache,
        )
        
        return ExecutionEngine(
            tool_registry=tool_registry,
            context_manager=context_manager,
        )
    
    else:
        # LEGACY: ContextCompactor path
        compactor = ContextCompactor(
            llm=llm_provider,
            max_context_tokens=config.agents.context.compaction.max_context_tokens,
            reserved_tokens=config.agents.context.compaction.reserved_tokens,
        )
        
        return ExecutionEngine(
            tool_registry=tool_registry,
            compactor=compactor,
        )
```

### ExecutionEngine Logic

```python
# src/codelab/server/agent/execution_engine.py
async def build_context(
    self,
    session: SessionState,
    prompt: str,
    system_prompt: str | None = None,
    mcp_manager: Any | None = None,
    content_parts: list[Any] | None = None,
    agent_scope: str = "single",
) -> AgentContext:
    """Build context с feature flag branching."""
    
    # Build history
    history = self.history_builder.build(session.history, system_prompt=system_prompt)
    history = self.sanitizer.sanitize(history)
    
    # Feature flag branch
    if self.context_manager is not None:
        # FCM path
        history = await self._build_via_fcm(session, system_prompt, agent_scope)
    elif self.compactor is not None:
        # Legacy path
        history, _, _ = await self.compactor.compact_if_needed(history)
    
    # ... rest of build_context ...
```

---

## 4. Canary Deployment

### Dynamic Rollout

```python
import hashlib

def is_fcm_enabled_for_session(
    session_id: str,
    config: Config,
    rollout_percent: int,
) -> bool:
    """Gradual rollout: включаем FCM для % сессий."""
    if not config.agents.context.enable_fcm:
        return False
    
    # Consistent hashing: session всегда в одной группе
    hash_val = int(hashlib.md5(session_id.encode()).hexdigest(), 16)
    return (hash_val % 100) < rollout_percent

# Usage в factory
fcm_enabled = is_fcm_enabled_for_session(
    session_id,
    config,
    rollout_percent=int(os.getenv("CODELAB_FCM_ROLLOUT_PERCENT", "100")),
)
```

### Rollout Schedule

| Week | Rollout % | Monitoring |
|------|-----------|------------|
| 1    | 0% (internal testing) | Dev/staging only |
| 2    | 5% (canary) | 48h observation |
| 3    | 25% | 48h observation |
| 4    | 50% | 48h observation |
| 5-6  | 100% | 1 week stability |

---

## 5. Monitoring

### Metrics

```python
# Feature flag state
metrics.gauge("fcm.enabled", 1 if fcm_enabled else 0)
metrics.gauge("fcm.ast_skeletonization_enabled", ...)
metrics.gauge("fcm.file_cache_enabled", ...)

# Rollout coverage
metrics.gauge("fcm.rollout_percent", rollout_percent)
metrics.gauge("fcm.sessions_enabled_count", enabled_sessions)
```

### Comparison Dashboard

Track FCM vs Legacy metrics side-by-side:

```python
metrics.timing("context_build.latency", duration, tags={"mode": "fcm"})
metrics.timing("context_build.latency", duration, tags={"mode": "legacy"})

metrics.gauge("context_build.tokens", token_count, tags={"mode": "fcm"})
metrics.gauge("context_build.tokens", token_count, tags={"mode": "legacy"})
```

---

## 6. Rollback

### Immediate Rollback

```bash
# Set environment variable
export CODELAB_FCM_ENABLED=false

# Reload server (graceful, no downtime)
systemctl reload codelab-server
```

### Partial Rollback

```bash
# Reduce rollout percentage
export CODELAB_FCM_ROLLOUT_PERCENT=5  # was 50
systemctl reload codelab-server
```

---

## 7. Testing

### Unit Tests

```python
def test_feature_flag_enabled():
    config = Config()
    config.agents.context.enable_fcm = True
    
    engine = create_execution_engine(tool_registry, config, llm, session_id)
    
    assert engine.context_manager is not None
    assert engine.compactor is None

def test_feature_flag_disabled():
    config = Config()
    config.agents.context.enable_fcm = False
    
    engine = create_execution_engine(tool_registry, config, llm, session_id)
    
    assert engine.context_manager is None
    assert engine.compactor is not None
```

### Integration Tests

```python
@pytest.mark.parametrize("fcm_enabled", [True, False])
async def test_build_context_with_feature_flag(fcm_enabled):
    config.agents.context.enable_fcm = fcm_enabled
    engine = create_execution_engine(...)
    
    context = await engine.build_context(session, prompt)
    
    assert context is not None
    assert len(context.conversation_history) > 0
```

---

## Связанные документы

- [MIGRATION_PLAN.md](./MIGRATION_PLAN.md) — rollout schedule details
- [ERROR_HANDLING.md](./ERROR_HANDLING.md) — error handling
- [PERFORMANCE_REQUIREMENTS.md](./PERFORMANCE_REQUIREMENTS.md) — SLOs
