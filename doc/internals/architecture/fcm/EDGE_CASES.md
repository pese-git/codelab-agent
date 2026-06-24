# FCM Edge Cases Specification

> **Версия:** 1.0  
> **Дата:** 24 июня 2026  
> **Для кого:** Разработчики, имплементирующие FCM

---

## Оглавление

1. [Огромный файл (> max_tokens)](#1-огромный-файл--max_tokens)
2. [Все элементы priority=10 (критические)](#2-все-элементы-priority10-критические)
3. [Скелет больше оригинала](#3-скелет-больше-оригинала)
4. [LLM Summarization Timeout](#4-llm-summarization-timeout)
5. [Cache Invalidation Race Condition](#5-cache-invalidation-race-condition)
6. [Empty Scope](#6-empty-scope)
7. [Duplicate Item ID](#7-duplicate-item-id)
8. [Negative or Zero max_tokens](#8-negative-or-zero-max_tokens)
9. [Non-Python files](#9-non-python-files)
10. [Async Cancellation](#10-async-cancellation)

---

## 1. Огромный файл (> max_tokens)

### Scenario

```python
await fcm.add_to_scope(
    "agent", 
    "huge_database.py",  # 50,000 токенов
    "file_content",
    huge_content,
    priority=5,
)
# scope.max_tokens = 4000
```

### Problem

Один файл не помещается в бюджет скоупа.

### Expected Behavior

**Option A: Truncate content (выбрано для MVP)**

```python
async def add_to_scope(
    self,
    scope_name: str,
    item_id: str,
    content_type: ContextType,
    content: str,
    priority: int = 5,
) -> None:
    """Добавить элемент в скоуп."""
    scope = self.scopes[scope_name]
    token_count = self.token_counter.count(content)
    
    if token_count > scope.max_tokens:
        logger.warning(
            "item_exceeds_max_tokens_truncating",
            item_id=item_id,
            original_tokens=token_count,
            max_tokens=scope.max_tokens,
        )
        
        # Truncate до max_tokens
        max_chars = scope.max_tokens * 4  # approximate
        truncated = content[:max_chars]
        truncated_tokens = self.token_counter.count(truncated)
        
        logger.info(
            "item_truncated",
            item_id=item_id,
            original_tokens=token_count,
            truncated_tokens=truncated_tokens,
        )
        
        content = truncated
        token_count = truncated_tokens
    
    item = ContextItem(...)
    scope.add(item)
```

**Option B: Reject (для post-MVP)**

```python
if token_count > scope.max_tokens:
    raise ValueError(
        f"Item '{item_id}' ({token_count} tokens) exceeds "
        f"scope max_tokens ({scope.max_tokens})"
    )
```

### Decision

**MVP:** Option A (graceful degradation)  
**Rationale:** Система не должна падать из-за одного большого файла

### Testing

```python
async def test_add_to_scope_huge_file():
    fcm = FederatedContextManager(token_counter=token_counter)
    await fcm.create_scope("agent", max_tokens=1000)
    
    huge = "x" * 10000  # ~2500 tokens
    
    await fcm.add_to_scope("agent", "huge.py", "file_content", huge)
    
    scope = fcm.scopes["agent"]
    item = scope.get("huge.py")
    
    assert item.token_count <= 1000
    assert len(item.content) < len(huge)
```

---

## 2. Все элементы priority=10 (критические)

### Scenario

```python
# Все элементы критические
await fcm.add_to_scope("agent", "system_prompt", ..., priority=10)  # 1000 tokens
await fcm.add_to_scope("agent", "user_task", ..., priority=10)      # 2000 tokens
await fcm.add_to_scope("agent", "critical_db.py", ..., priority=10) # 8000 tokens
await fcm.add_to_scope("agent", "critical_api.py", ..., priority=10) # 5000 tokens
# Total: 16,000 tokens
# max_tokens: 4000
```

### Problem

Critical items (priority >= 10) нельзя вытеснить, но их сумма превышает бюджет.

### Expected Behavior

**Raise exception при optimize_and_build_payload:**

```python
async def optimize_and_build_payload(self, scope_name: str) -> list[LLMMessage]:
    scope = self.scopes[scope_name]
    
    system_items = [item for item in scope.registry.values() if item.priority >= 10]
    system_tokens = sum(item.token_count for item in system_items)
    
    if system_tokens > scope.max_tokens:
        logger.error(
            "critical_items_exceed_budget",
            scope_name=scope_name,
            system_tokens=system_tokens,
            max_tokens=scope.max_tokens,
            critical_items=[item.id for item in system_items],
        )
        raise ValueError(
            f"Critical items ({system_tokens} tokens) exceed scope budget ({scope.max_tokens} tokens). "
            f"Reduce critical items or increase max_tokens."
        )
    
    # ... continue ...
```

### Rationale

Configuration error → fail fast, explicit

### Alternative (post-MVP)

Truncate последний критический элемент:

```python
if system_tokens > scope.max_tokens:
    logger.warning("truncating_last_critical_item", ...)
    last_item = system_items[-1]
    # Truncate last_item...
```

### Testing

```python
async def test_critical_items_exceed_budget():
    fcm = FederatedContextManager(token_counter=token_counter)
    await fcm.create_scope("agent", max_tokens=1000)
    
    # Add critical items > budget
    await fcm.add_to_scope("agent", "sys", "system_rules", "x" * 2000, priority=10)
    await fcm.add_to_scope("agent", "file", "file_content", "y" * 3000, priority=10)
    
    with pytest.raises(ValueError, match="Critical items .* exceed scope budget"):
        await fcm.optimize_and_build_payload("agent")
```

---

## 3. Скелет больше оригинала

### Scenario

```python
# Minified код
original = "a=lambda x:x+1;b=lambda y:y*2"  # 10 tokens

# After skeletonization
skeleton = """
# [СЖАТО: структура файла minified.py]
a = lambda x: x + 1
b = lambda y: y * 2
""".strip()  # 15 tokens

# Парадокс: skeleton_tokens > original_tokens
```

### Problem

AST-скелетирование может увеличивать размер для minified/compact кода.

### Expected Behavior

**Detection + fallback to original:**

```python
async def _compact_with_skeleton(self, history):
    result = []
    for msg in history:
        if self._is_file_content(msg):
            skeleton = self.skeletonizer.skeletonize(msg.content, file_id)
            skeleton_tokens = self.token_counter.count(skeleton)
            original_tokens = self.token_counter.count(msg.content)
            
            if skeleton_tokens >= original_tokens:
                logger.warning(
                    "skeleton_not_beneficial",
                    file_id=file_id,
                    original_tokens=original_tokens,
                    skeleton_tokens=skeleton_tokens,
                )
                result.append(msg)  # use original
            else:
                result.append(LLMMessage(role=msg.role, content=skeleton))
        else:
            result.append(msg)
    return result
```

### Metrics

```python
metrics.counter("fcm.skeleton_not_beneficial")
```

Alert if > 20% файлов имеют skeleton >= original (означает проблему с алгоритмом).

### Testing

```python
def test_skeleton_not_beneficial():
    skeletonizer = PythonASTSkeletonizer()
    token_counter = create_token_counter()
    
    minified = "a=lambda x:x+1"
    skeleton = skeletonizer.skeletonize(minified, "min.py")
    
    if token_counter.count(skeleton) >= token_counter.count(minified):
        # Should use original
        assert True
```

---

## 4. LLM Summarization Timeout

### Scenario

```python
# LLM API медленный или перегружен
await compactor._summarize_conversation(large_history)
# Timeout после 10 секунд
```

### Expected Behavior

```python
try:
    response = await asyncio.wait_for(
        self.llm.create_completion(request),
        timeout=10.0,
    )
    summary = response.text
    return start + [summary_msg] + end

except asyncio.TimeoutError:
    logger.warning(
        "summarization_timeout",
        timeout_sec=10,
        middle_count=len(middle),
    )
    # Fallback: удаляем middle без summarization
    return start + end
```

### Impact

- ✅ Система не падает
- ⚠️ Middle messages удалены (потеря контекста)

### Metrics

```python
metrics.counter("fcm.summarization_timeout")
```

Alert if > 5% (LLM проблема).

### Testing

```python
async def test_summarization_timeout():
    mock_llm = MagicMock()
    mock_llm.create_completion = AsyncMock(side_effect=asyncio.TimeoutError())
    
    compactor = DefaultContextCompactor(llm=mock_llm, ...)
    history = make_large_history(20)
    
    result = await compactor._summarize_conversation(history)
    
    assert len(result) < len(history)  # middle removed
    assert result[0] == history[0]     # start preserved
    assert result[-1] == history[-1]   # end preserved
```

---

## 5. Cache Invalidation Race Condition

### Scenario

```python
# Concurrent operations:
# Thread 1: Read  file → cache.set("db.py", old_content)
# Thread 2: Write file → cache.invalidate("db.py")
# Thread 1: (delayed) cache.set("db.py", old_content)  # overwrites invalidation!
```

### Problem

Stale cache после записи из-за race condition.

### Mitigation Strategies

**Option A: Version-based cache (для post-MVP)**

```python
cache.set("db.py", content, version=3)
cache.invalidate("db.py", min_version=4)
```

**Option B: Accept eventual consistency (для MVP)**

- Документировать ограничение: FileContentCache может содержать stale data
- Acceptable для агентов (редко читают сразу после записи)
- TTL expiration (optional): очищать кэш после 5 минут

### Decision

**MVP:** Option B (document limitation)  
**Post-MVP:** Option A (если становится проблемой)

### Documentation

```python
# src/codelab/server/agent/context/file_cache.py
class FileContentCache(ABC):
    """Кэш содержимого файлов.
    
    Warning: Concurrent write → read может привести к stale cache
    в редких случаях. Acceptable для agent use case.
    """
```

---

## 6. Empty Scope

### Scenario

```python
scope = await fcm.create_scope("agent", max_tokens=4000)
# Ничего не добавляем
payload = await fcm.optimize_and_build_payload("agent")
```

### Expected Behavior

```python
# Возвращаем пустой список
assert payload == []
```

### Note

ExecutionEngine должен гидр атировать скоуп через `hydrate_from_history()` перед использованием.

### Testing

```python
async def test_empty_scope():
    fcm = FederatedContextManager()
    await fcm.create_scope("agent", max_tokens=4000)
    
    payload = await fcm.optimize_and_build_payload("agent")
    
    assert payload == []
```

---

## 7. Duplicate Item ID

### Scenario

```python
await fcm.add_to_scope("agent", "db.py", "file_content", content_v1, priority=5)
await fcm.add_to_scope("agent", "db.py", "file_content", content_v2, priority=7)
```

### Expected Behavior

**Option A: Overwrite (выбрано для MVP)**

```python
def add(self, item: ContextItem) -> None:
    existing = item.id in self.registry
    self.registry[item.id] = item  # overwrite
    logger.debug(
        "item_added_or_updated",
        item_id=item.id,
        overwrote=existing,
    )
```

**Semantic:** Update existing item with new content/priority.

**Option B: Raise exception**

```python
if item.id in self.registry:
    raise ValueError(f"Item '{item.id}' already exists")
```

### Decision

**MVP:** Option A (simple, semantic update)

### Testing

```python
async def test_duplicate_item_id_overwrites():
    fcm = FederatedContextManager()
    await fcm.create_scope("agent", max_tokens=4000)
    
    await fcm.add_to_scope("agent", "file.py", "file_content", "v1", priority=5)
    await fcm.add_to_scope("agent", "file.py", "file_content", "v2", priority=7)
    
    scope = fcm.scopes["agent"]
    item = scope.get("file.py")
    
    assert item.content == "v2"
    assert item.priority == 7
```

---

## 8. Negative or Zero max_tokens

### Scenario

```python
await fcm.create_scope("agent", max_tokens=0)    # or -100
```

### Expected Behavior

**Fail fast at creation:**

```python
def __init__(self, scope_name: str, max_tokens: int = 4000) -> None:
    if max_tokens <= 0:
        raise ValueError(f"max_tokens must be positive, got {max_tokens}")
    self.scope_name = scope_name
    self.max_tokens = max_tokens
    self.registry: dict[str, ContextItem] = {}
```

### Rationale

Configuration error → crash early.

### Testing

```python
async def test_create_scope_zero_max_tokens():
    fcm = FederatedContextManager()
    
    with pytest.raises(ValueError, match="max_tokens must be positive"):
        await fcm.create_scope("agent", max_tokens=0)
```

---

## 9. Non-Python files

### Scenario

```python
await fcm.add_to_scope("agent", "config.json", "file_content", json_content)
# Попытка AST-скелетирования
```

### Expected Behavior

**PythonASTSkeletonizer** проверяет язык:

```python
def skeletonize(self, code: str, file_id: str = "", language: str = "python") -> str:
    if language != "python":
        logger.debug("skeletonization_not_supported", language=language, file_id=file_id)
        return f"# Скелетирование для {language} не поддерживается\n{code}"
    
    # ... continue with AST ...
```

### Alternative

Определять язык по расширению файла:

```python
def _detect_language(file_id: str) -> str:
    ext = file_id.split('.')[-1].lower()
    return {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
    }.get(ext, "unknown")
```

### Decision

**MVP:** Return original для non-Python  
**Post-MVP:** Добавить JavaScriptSkeletonizer, TypeScriptSkeletonizer (extends CodeSkeletonizer)

---

## 10. Async Cancellation

### Scenario

```python
task = asyncio.create_task(fcm.optimize_and_build_payload("agent"))
# ...
task.cancel()  # User cancelled request
```

### Expected Behavior

**Graceful cancellation:**

```python
async def optimize_and_build_payload(self, scope_name: str) -> list[LLMMessage]:
    try:
        # Long-running operations
        ...
    except asyncio.CancelledError:
        logger.info("optimize_and_build_payload_cancelled", scope_name=scope_name)
        raise  # Re-raise to propagate cancellation
```

### Testing

```python
async def test_optimize_and_build_payload_cancellation():
    fcm = FederatedContextManager(...)
    await fcm.create_scope("agent", max_tokens=4000)
    
    task = asyncio.create_task(fcm.optimize_and_build_payload("agent"))
    await asyncio.sleep(0.01)
    task.cancel()
    
    with pytest.raises(asyncio.CancelledError):
        await task
```

---

## Testing Requirements Summary

Для каждого edge case:

- [ ] Unit test с expected behavior
- [ ] Log message verification
- [ ] Metrics verification (где applicable)
- [ ] Documentation в docstring

**Coverage target:** 100% для edge case handling блоков.

---

## Связанные документы

- [ERROR_HANDLING.md](./ERROR_HANDLING.md) — error handling strategy
- [MIGRATION_PLAN.md](./MIGRATION_PLAN.md) — migration phases
- [ARCHITECTURE.md](./ARCHITECTURE.md) — overall architecture
