# FCM Performance Requirements & SLOs

> **Версия:** 1.0  
> **Дата:** 24 июня 2026

---

## 1. Service Level Objectives (SLOs)

### 1.1. Latency Requirements

| Operation | p50 | p95 | p99 | Max |
|-----------|-----|-----|-----|-----|
| `build_context()` | < 50ms | < 200ms | < 500ms | < 2s |
| `add_to_scope()` | < 5ms | < 20ms | < 50ms | < 200ms |
| `share_item()` | < 1ms | < 5ms | < 10ms | < 50ms |
| `optimize_and_build_payload()` | < 100ms | < 500ms | < 1s | < 5s |

#### Breakdown: optimize_and_build_payload

| Sub-operation | Budget (p95) | Note |
|---------------|--------------|------|
| Sort by priority | < 10ms | O(n log n) на 100 items |
| Token counting | < 50ms | Multiple items |
| AST skeletonization | < 200ms | Самая тяжёлая операция |
| LLM summarization | < 2s | Если нужна |

### 1.2. Throughput Requirements

- **Concurrent sessions:** 1000 sessions
- **Requests per second:** 100 build_context calls/sec
- **Cache hit rate:** > 80% (FileContentCache)

### 1.3. Memory Requirements

| Component | Per Session | 1000 Sessions | Max |
|-----------|-------------|---------------|-----|
| FileContentCache | < 1 MB | < 1 GB | 2 GB |
| AgentContextScope | < 500 KB | < 500 MB | 1 GB |
| **Total FCM overhead** | **< 2 MB** | **< 2 GB** | **4 GB** |

---

## 2. Baseline (Legacy ContextCompactor)

### Current Performance

Измерено из существующих тестов:

```python
# Existing system
legacy_build_context_p50 = 30ms
legacy_build_context_p95 = 150ms
legacy_memory_per_session = 500KB
```

### Acceptable Regression

| Metric | Legacy | FCM Target | Max Regression |
|--------|--------|------------|----------------|
| Latency p50 | 30ms | < 45ms | +50% |
| Latency p95 | 150ms | < 225ms | +50% |
| Memory | 500KB | < 1MB | +100% |

**Rationale:** Improved quality (AST, priorities) компенсирует latency increase.

---

## 3. Benchmarking Strategy

### 3.1. Test Scenarios

#### Scenario 1: Small Session (baseline)

```python
# 10 messages, 2000 tokens total
history = [
    LLMMessage(role="system", content="..." * 100),
    LLMMessage(role="user", content="..." * 100),
    # ... 8 more
]

# Expected:
# - p95 < 50ms
# - Memory < 100KB
```

#### Scenario 2: Medium Session

```python
# 50 messages, 10000 tokens
# Expected:
# - p95 < 200ms
# - Memory < 500KB
```

#### Scenario 3: Large Session (stress test)

```python
# 200 messages, 100000 tokens → triggers compaction
# Expected:
# - p95 < 1000ms
# - Memory < 2MB
```

#### Scenario 4: Huge File

```python
# 1 file, 50000 tokens → AST skeletonization
await fcm.add_to_scope("agent", "huge.py", "file_content", huge_code)

# Expected:
# - AST parsing p95 < 500ms (for 5000 LOC)
# - Skeleton size < 10% of original
```

### 3.2. Benchmark Script

```python
# benchmarks/fcm_performance.py
import time
import statistics
import asyncio
from codelab.server.agent.context import FederatedContextManager

async def benchmark_build_context(iterations=1000):
    """Benchmark optimize_and_build_payload."""
    fcm = FederatedContextManager(...)
    await fcm.create_scope("agent", max_tokens=4000)
    
    # Add test data
    await fcm.add_to_scope("agent", "file.py", "file_content", test_code)
    await fcm.add_to_scope("agent", "prompt", "user_prompt", test_prompt)
    
    timings = []
    for _ in range(iterations):
        start = time.perf_counter()
        await fcm.optimize_and_build_payload("agent")
        duration = (time.perf_counter() - start) * 1000  # ms
        timings.append(duration)
    
    print(f"p50: {statistics.median(timings):.1f}ms")
    print(f"p95: {statistics.quantiles(timings, n=20)[18]:.1f}ms")
    print(f"p99: {statistics.quantiles(timings, n=100)[98]:.1f}ms")
    print(f"max: {max(timings):.1f}ms")

if __name__ == "__main__":
    asyncio.run(benchmark_build_context())
```

### 3.3 Memory Profiling

```python
# benchmarks/fcm_memory.py
import tracemalloc

tracemalloc.start()

# Simulate 1000 sessions
cache_registry = SessionFileCacheRegistry()
fcms = []

for i in range(1000):
    cache = cache_registry.get_or_create(f"session_{i}")
    fcm = FederatedContextManager(file_cache=cache, ...)
    await fcm.create_scope("agent", max_tokens=4000)
    await fcm.add_to_scope("agent", "file.py", "file_content", test_code)
    fcms.append(fcm)

current, peak = tracemalloc.get_traced_memory()
print(f"Current: {current / 1024 / 1024:.1f} MB")
print(f"Peak: {peak / 1024 / 1024:.1f} MB")
print(f"Per session: {peak / 1000 / 1024:.1f} KB")

tracemalloc.stop()
```

---

## 4. Performance Targets

### Phase 1: MVP (acceptable)

- Meet SLOs для 90% requests
- No severe regressions (> 100%) vs legacy
- Memory < 4GB для 1000 sessions

### Phase 2: Optimization (if needed)

**Techniques:**
- Lazy AST parsing (parse only when compaction needed)
- Batch token counting (tiktoken batch API)
- Async skeletonization (non-blocking)
- Cache AST trees (avoid re-parsing same file)

### Phase 3: Advanced (post-MVP)

**Techniques:**
- Incremental token counting (only changed parts)
- Pre-computed skeletons (background job)
- Streaming context building (start LLM request early)
- Shared file cache across sessions (with isolation)

---

## 5. Monitoring

### 5.1. Production Metrics

```python
# Latency
metrics.timing("fcm.build_context.latency", duration_ms)
metrics.timing("fcm.ast_skeletonize.latency", duration_ms)
metrics.timing("fcm.token_count.latency", duration_ms)
metrics.timing("fcm.optimize_and_build_payload.latency", duration_ms)

# Throughput
metrics.counter("fcm.build_context.calls")
metrics.counter("fcm.optimize_and_build_payload.calls")

# Memory
metrics.gauge("fcm.cache.size_bytes", cache_size)
metrics.gauge("fcm.scope.token_count", token_count)
metrics.gauge("fcm.memory_per_session_mb", memory_mb)

# Cache performance
metrics.counter("fcm.cache.hit")
metrics.counter("fcm.cache.miss")
metrics.counter("fcm.cache.eviction")
metrics.gauge("fcm.cache.hit_rate", hit_rate)

# Skeletonization
metrics.histogram("fcm.skeleton_savings_percent", savings)
metrics.counter("fcm.skeleton_applied")
metrics.counter("fcm.skeleton_not_beneficial")
```

### 5.2. Alerts

```yaml
# alerts.yaml

- alert: FCM_Latency_P95_High
  expr: fcm_build_context_latency_p95 > 500ms
  for: 5m
  severity: warning
  action: Investigate slow operations

- alert: FCM_Latency_P99_Critical
  expr: fcm_build_context_latency_p99 > 2000ms
  for: 2m
  severity: critical
  action: Consider rollback

- alert: FCM_Memory_Per_Session_High
  expr: fcm_memory_per_session_mb > 5
  for: 10m
  severity: warning
  action: Check for memory leaks

- alert: FCM_Cache_Hit_Rate_Low
  expr: fcm_cache_hit_rate < 0.8
  for: 10m
  severity: info
  action: Increase cache size or investigate access patterns

- alert: FCM_AST_Latency_High
  expr: fcm_ast_skeletonize_latency_p95 > 500ms
  for: 5m
  severity: warning
  action: Check for large files or optimize parser
```

---

## 6. Acceptance Criteria

### Before Production Rollout

- [ ] All benchmarks pass (p50/p95/p99 within SLOs)
- [ ] Memory usage < 2MB per session
- [ ] No regressions > 50% vs legacy (same scenarios)
- [ ] Load test: 1000 concurrent sessions stable for 1h
- [ ] Cache hit rate > 80% in realistic workload

### Before 100% Rollout

- [ ] 1 week canary (5%) with no incidents
- [ ] Performance metrics equal or better than legacy
- [ ] Error rate < 0.1%
- [ ] No memory leaks observed

---

## 7. Performance Degradation Response

### Triggers

1. **Latency p95 > 2x SLO** (> 400ms for build_context)
2. **Memory > 2x target** (> 4MB per session)
3. **Cache hit rate < 50%**

### Actions

```
Detect degradation
    ↓
Check dashboard (which operation slow?)
    ↓
AST parsing? ──Yes──> Disable AST temporarily (feature flag)
    │                 Investigate large files
    No
    ↓
Token counting? ──Yes──> Switch to ApproximateTokenCounter
    │                    Check tiktoken performance
    No
    ↓
Summarization? ──Yes──> Check LLM API latency
    │                   Increase timeout or disable summarize
    No
    ↓
General slowdown? ──Yes──> Rollback to legacy
                          Post-mortem analysis
```

---

## Связанные документы

- [MIGRATION_PLAN.md](./MIGRATION_PLAN.md) — rollout phases
- [ERROR_HANDLING.md](./ERROR_HANDLING.md) — error scenarios
- [FEATURE_FLAGS.md](./FEATURE_FLAGS.md) — configuration
