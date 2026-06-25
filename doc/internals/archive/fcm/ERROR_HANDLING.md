# FCM Error Handling Strategy

> **ARCHIVED.** Этот документ архивирован. Каноническая документация — в [`doc/internals/context-manager/`](../../context-manager/). См. также [ADR-002](../adr/ADR-002-context-manager-consolidation.md).


> **Версия:** 1.0  
> **Дата:** 24 июня 2026  
> **Для кого:** Разработчики, имплементирующие FCM

---

## Оглавление

1. [Принципы](#1-принципы)
2. [Слой 1: Утилиты](#2-слой-1-утилиты)
3. [Слой 2: Сжатие](#3-слой-2-сжатие)
4. [Слой 3: Оркестрация](#4-слой-3-оркестрация)
5. [Testing Strategy](#5-testing-strategy)
6. [Monitoring & Alerting](#6-monitoring--alerting)
7. [Incident Response](#7-incident-response)

---

## 1. Принципы

### 1.1. Core Principles

1. **Graceful Degradation** — система продолжает работать при partial failure
2. **Observable Failures** — все ошибки логируются с context (structlog)
3. **No Silent Failures** — запрещены конструкции `except: pass`
4. **Fail Fast for Config Errors** — ошибки конфигурации → crash at startup
5. **Recoverable Runtime Errors** — ошибки во время работы → fallback + log

### 1.2. Error Categories

| Category | Severity | Action | Example |
|----------|----------|--------|---------|
| **Configuration** | Critical | Crash at startup | Invalid max_tokens |
| **Runtime Recoverable** | Warning | Fallback + log | AST parse failure |
| **Runtime Critical** | Error | Raise exception | Scope not found |
| **Performance Degradation** | Info | Log metrics | Token count inaccurate |

### 1.3. Logging Standard

**Используем structlog для structured logging:**

```python
import structlog

logger = structlog.get_logger(__name__)

# Good: structured context
logger.warning(
    "ast_parse_failed",
    file_id=file_id,
    error_type=type(e).__name__,
    line_number=e.lineno if hasattr(e, 'lineno') else None,
)

# Bad: unstructured
logger.warning(f"AST parse failed for {file_id}: {e}")
```

**Required fields для всех error logs:**
- `event` — короткое имя события (snake_case)
- `error_type` — тип exception (если есть)
- `context` — domain-specific поля

---

## 2. Слой 1: Утилиты

### 2.1. TokenCounter Errors

#### Error: tiktoken ImportError

**Scenario:** библиотека tiktoken не установлена

**Behavior:**
```python
# src/codelab/server/agent/context/token_counter.py
def create_token_counter() -> TokenCounter:
    """Factory Method: создать лучший доступный TokenCounter."""
    try:
        import tiktoken
        logger.info("token_counter_mode", mode="tiktoken")
        return TiktokenCounter()
    except ImportError:
        logger.warning(
            "tiktoken_not_available_using_fallback",
            fallback="ApproximateTokenCounter",
        )
        return ApproximateTokenCounter()
```

**Impact:**
- ✅ Система работает (fallback)
- ⚠️ Точность снижается до ~70-130%
- ⚠️ Risk: token limit miscalculation → потеря контекста или OOM

**Mitigation:**
```python
# Increase reserved_tokens buffer при использовании approximate counter
if isinstance(token_counter, ApproximateTokenCounter):
    reserved_tokens = reserved_tokens * 2  # double buffer
```

#### Error: tiktoken encoding failure

**Scenario:** tiktoken.encode() падает на specific input (rare)

**Behavior:**
```python
class TiktokenCounter(TokenCounter):
    def count(self, content: str) -> int:
        if not content:
            return 0
        
        try:
            return len(self._encoding.encode(content))
        except Exception as e:
            # Fallback to approximate (graceful degradation)
            logger.error(
                "tiktoken_encoding_failed_using_fallback",
                content_length=len(content),
                error_type=type(e).__name__,
                exc_info=e,
            )
            return len(content) // 4  # approximate
```

**Impact:**
- ✅ Single item affected (не весь batch)
- ⚠️ Inaccurate token count для этого item

**Testing:**
```python
def test_tiktoken_counter_encoding_failure():
    counter = TiktokenCounter()
    # Mock encoding.encode to raise
    with patch.object(counter._encoding, 'encode', side_effect=UnicodeDecodeError(...)):
        result = counter.count("problematic text")
        assert result > 0  # fallback сработал
```

---

### 2.2. CodeSkeletonizer Errors

#### Error: AST parsing SyntaxError

**Scenario:** файл содержит invalid Python syntax

**Behavior:**
```python
# src/codelab/server/agent/context/ast_skeletonizer.py
class PythonASTSkeletonizer(CodeSkeletonizer):
    def skeletonize(self, code: str, file_id: str = "", language: str = "python") -> str:
        if language != "python":
            logger.debug("skeletonization_not_supported", language=language)
            return f"# Скелетирование для {language} не поддерживается\n{code}"
        
        try:
            tree = ast.parse(code)
            visitor = _ASTVisitor()
            visitor.visit(tree)
            skeleton = "\n".join(visitor.result)
            return f"# [СЖАТО: структура файла {file_id}]\n{skeleton}"
        
        except SyntaxError as e:
            logger.warning(
                "ast_parse_syntax_error",
                file_id=file_id,
                line_number=e.lineno,
                offset=e.offset,
                error_msg=e.msg,
            )
            # Return error marker + truncated original
            return (
                f"# [ОШИБКА: Invalid Python syntax at line {e.lineno}]\n"
                f"# {e.msg}\n"
                f"{code[:500]}..."  # first 500 chars
            )
        
        except Exception as e:
            logger.error(
                "ast_parse_unexpected_error",
                file_id=file_id,
                error_type=type(e).__name__,
                exc_info=e,
            )
            # Safe fallback: return original code truncated
            return f"# [ОШИБКА: Failed to skeletonize]\n{code[:500]}..."
```

**Decision Tree: Что возвращать при SyntaxError?**

```
AST parsing failed (SyntaxError)?
├─ Yes: Is file small (<1000 tokens)?
│  ├─ Yes → Return original code (fits in budget)
│  │        logger.info("skeletonization_skipped_small_file")
│  │
│  └─ No → Return error message + first 500 chars
│           logger.warning("skeletonization_failed_returning_truncated")
│
└─ No → Return skeleton
```

**Implementation:**
```python
def skeletonize(self, code: str, file_id: str = "", language: str = "python") -> str:
    try:
        # ... AST logic ...
    except SyntaxError as e:
        # Check if original is small enough
        approx_tokens = len(code) // 4
        if approx_tokens < 1000:
            logger.info(
                "skeletonization_failed_but_small_returning_original",
                file_id=file_id,
                approx_tokens=approx_tokens,
            )
            return code  # original fits
        else:
            logger.warning(
                "skeletonization_failed_returning_truncated",
                file_id=file_id,
                approx_tokens=approx_tokens,
            )
            return f"# [ERROR: Syntax error]\n{code[:2000]}..."  # ~500 tokens
```

**Impact:**
- ✅ Система не падает
- ⚠️ For large invalid files: loss of context (only первые 500 chars)

**Testing:**
```python
def test_ast_skeletonizer_syntax_error_small_file():
    skeletonizer = PythonASTSkeletonizer()
    invalid_code = "def foo(:\n    pass"  # syntax error, ~10 tokens
    result = skeletonizer.skeletonize(invalid_code, "bad.py")
    assert result == invalid_code  # returns original

def test_ast_skeletonizer_syntax_error_large_file():
    skeletonizer = PythonASTSkeletonizer()
    invalid_code = "def foo(:\n" + "    pass\n" * 10000  # huge invalid file
    result = skeletonizer.skeletonize(invalid_code, "huge_bad.py")
    assert "ERROR" in result
    assert len(result) < len(invalid_code)  # truncated
```

---

### 2.3. FileContentCache Errors

#### Error: Cache full (LRU eviction)

**Scenario:** кэш достиг max_size, нужно вытеснить старый элемент

**Behavior:**
```python
# src/codelab/server/agent/context/file_cache.py
class InMemoryFileCache(FileContentCache):
    def set(self, path: str, content: str) -> None:
        if path in self._cache:
            self._cache.move_to_end(path)  # touch
        self._cache[path] = content
        
        if len(self._cache) > self._max_size:
            evicted_path, _ = self._cache.popitem(last=False)  # LRU eviction
            logger.debug(
                "file_cache_evicted",
                evicted_path=evicted_path,
                cache_size=len(self._cache),
                max_size=self._max_size,
            )
```

**Impact:**
- ✅ Minimal — следующее чтение будет RPC miss вместо cache hit
- ⚠️ Slight latency increase для evicted файлов

**Mitigation:**
- Adjust `max_size` based on memory profiling
- Monitor cache hit rate: alert if < 80%

**Testing:**
```python
def test_file_cache_lru_eviction():
    cache = InMemoryFileCache(max_size=2)
    cache.set("a.py", "content_a")
    cache.set("b.py", "content_b")
    cache.set("c.py", "content_c")  # evicts a.py
    
    assert cache.get("a.py") is None  # evicted
    assert cache.get("b.py") == "content_b"
    assert cache.get("c.py") == "content_c"
```

#### Error: FileCacheDecorator failure (ветка `_on_write`)

**Scenario:** `FileContentCache.invalidate()` падает (unexpected) при
успешной записи файла.

**Behavior:** ветка `_on_write` обёрнута в `try/except`, ошибка логируется,
но не пробрасывается — stale cache лучше, чем упавший tool executor.

```python
# src/codelab/server/tools/executors/decorators/file_cache.py
def _on_write(self, session: SessionState, path: str) -> None:
    try:
        self._file_cache.invalidate(path)
        logger.debug(
            "file_cache_invalidated",
            session_id=session.session_id,
            path=path,
        )
    except Exception as e:
        # Stale cache лучше, чем упавший tool execution
        logger.error(
            "file_cache_invalidation_failed",
            path=path,
            error_type=type(e).__name__,
            exc_info=e,
        )
        # Continue без raise — tool execution успешен
```

> Ветки `_on_read` и `_on_terminal` имеют такую же семантику: ошибки
> регистрации/кэширования не должны срывать успешный tool execution.

**Impact:**
- ✅ Tool execution не affected
- ⚠️ Stale cache до следующей write операции

**Acceptable:** Agents редко читают файл сразу после записи (temporal locality низкая)

**Testing:**
```python
async def test_file_cache_decorator_invalidation_failure():
    # Mock file_cache.invalidate to raise
    mock_cache = MagicMock()
    mock_cache.invalidate.side_effect = RuntimeError("Cache error")

    decorator = FileCacheDecorator(base_executor, mock_cache)

    # Should not raise despite invalidation failure
    result = await decorator.execute(
        session=MagicMock(session_id="s1"),
        arguments={"operation": "write", "path": "test.py"},
    )

    assert result.success  # tool execution succeeded
```

---

## 3. Слой 2: Сжатие

### 3.1. DefaultContextCompactor Errors

#### Error: Skeletonization failed для критичного файла

**Scenario:** AST parsing падает, но файл критически важен для контекста

**Behavior:**
```python
# src/codelab/server/agent/context/compactor.py
class DefaultContextCompactor(ContextCompactor):
    async def _compact_with_skeleton(
        self,
        history: list[LLMMessage],
    ) -> list[LLMMessage]:
        """Фаза 2: AST-скелетирование file_content."""
        result = []
        
        for msg in history:
            if self._is_file_content(msg) and self.enable_skeletonization:
                try:
                    skeleton = self.skeletonizer.skeletonize(
                        msg.content,
                        file_id=self._extract_file_id(msg),
                    )
                    skeleton_tokens = self.token_counter.count(skeleton)
                    original_tokens = self.token_counter.count(msg.content)
                    
                    # Edge case: skeleton больше оригинала
                    if skeleton_tokens >= original_tokens:
                        logger.warning(
                            "skeleton_not_beneficial",
                            file_id=self._extract_file_id(msg),
                            original_tokens=original_tokens,
                            skeleton_tokens=skeleton_tokens,
                        )
                        result.append(msg)  # use original
                    else:
                        # Use skeleton
                        result.append(LLMMessage(role=msg.role, content=skeleton))
                        logger.info(
                            "skeleton_applied",
                            file_id=self._extract_file_id(msg),
                            original_tokens=original_tokens,
                            skeleton_tokens=skeleton_tokens,
                            savings_percent=round((1 - skeleton_tokens / original_tokens) * 100),
                        )
                
                except Exception as e:
                    logger.error(
                        "skeletonization_failed_using_original",
                        file_id=self._extract_file_id(msg),
                        error_type=type(e).__name__,
                        exc_info=e,
                    )
                    result.append(msg)  # fallback to original
            else:
                result.append(msg)
        
        return result
```

**Impact:**
- ✅ Система не падает
- ⚠️ Original file включён в контекст (может превысить бюджет)

**Cascading behavior:**
- Если после skeletonization fallback всё равно превышает бюджет → Фаза 3 (Summarize)

#### Error: LLM Summarization timeout

**Scenario:** LLM запрос занимает > timeout

**Behavior:**
```python
async def _summarize_conversation(
    self,
    history: list[LLMMessage],
) -> list[LLMMessage]:
    """Фаза 3: LLM-суммаризация."""
    if len(history) <= _MIN_HISTORY_LENGTH:
        return list(history)
    
    keep_start = 2
    keep_end = 3
    start = history[:keep_start]
    end = history[-keep_end:]
    middle = history[keep_start:-keep_end]
    
    if not middle:
        return list(history)
    
    if not self.llm:
        logger.debug("summarization_skipped_no_llm")
        return start + end  # удаляем middle
    
    # Format для суммаризации
    middle_text = "\n".join(
        f"[{msg.role}] {msg.content or ''}" for msg in middle
    )
    
    prompt = (
        "Summarize the following conversation concisely. "
        "Preserve key information, decisions, and context. "
        "Keep it under 200 words.\n\n"
        f"Conversation:\n{middle_text}"
    )
    
    try:
        request = CompletionRequest(
            model=self.model,
            messages=[LLMMessage(role="user", content=prompt)],
            max_tokens=500,
            temperature=0.0,
        )
        
        # Add timeout
        response = await asyncio.wait_for(
            self.llm.create_completion(request),
            timeout=10.0,  # 10 sec timeout
        )
        
        summary = response.text
        summary_msg = LLMMessage(
            role="assistant",
            content=f"[Summary of {len(middle)} messages] {summary}",
        )
        
        logger.info(
            "conversation_summarized",
            middle_messages_count=len(middle),
            summary_length=len(summary),
        )
        
        return start + [summary_msg] + end
    
    except asyncio.TimeoutError:
        logger.warning(
            "summarization_timeout",
            timeout_sec=10,
            middle_messages_count=len(middle),
        )
        return start + end  # fallback: прямое удаление
    
    except Exception as e:
        logger.error(
            "summarization_failed",
            error_type=type(e).__name__,
            exc_info=e,
        )
        return start + end  # fallback
```

**Impact:**
- ✅ Система не падает
- ⚠️ Middle messages удалены (потеря контекста)

**Metrics:**
- Track: `summarization_timeout_rate`
- Alert if > 5% (означает LLM перегружен или медленен)

**Testing:**
```python
async def test_summarization_timeout():
    mock_llm = MagicMock()
    mock_llm.create_completion = AsyncMock(
        side_effect=asyncio.TimeoutError(),
    )
    
    compactor = DefaultContextCompactor(llm=mock_llm, ...)
    history = make_large_history(20)
    
    result = await compactor._summarize_conversation(history)
    
    # Should return start + end (middle removed)
    assert len(result) < len(history)
    assert result[0] == history[0]  # start preserved
    assert result[-1] == history[-1]  # end preserved
```

---

## 4. Слой 3: Оркестрация

### 4.1. FederatedContextManager Errors

#### Error: Scope не существует

**Scenario:** вызов `optimize_and_build_payload()` для несуществующего скоупа

**Behavior:**
```python
# src/codelab/server/agent/context/manager.py
class FederatedContextManager(ContextManager):
    async def optimize_and_build_payload(
        self,
        scope_name: str,
    ) -> list[LLMMessage]:
        """Сформировать payload для LLM."""
        scope = self.scopes.get(scope_name)
        
        if scope is None:
            available_scopes = list(self.scopes.keys())
            logger.error(
                "scope_not_found",
                scope_name=scope_name,
                available_scopes=available_scopes,
            )
            raise ValueError(
                f"Scope '{scope_name}' not found. "
                f"Available scopes: {available_scopes}. "
                f"Create it first with create_scope()."
            )
        
        # ... continue ...
```

**Rationale:** Configuration error → fail fast

**Not recoverable:** Caller должен создать скоуп перед использованием

**Testing:**
```python
async def test_optimize_and_build_payload_scope_not_found():
    fcm = FederatedContextManager()
    
    with pytest.raises(ValueError, match="Scope 'nonexistent' not found"):
        await fcm.optimize_and_build_payload("nonexistent")
```

#### Error: Элемент превышает max_tokens

**Scenario:** add_to_scope() с item_size > scope.max_tokens

**Behavior:**
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
    if scope_name not in self.scopes:
        await self.create_scope(scope_name)
    
    scope = self.scopes[scope_name]
    token_count = self.token_counter.count(content)
    
    # Edge case: item > max_tokens
    if token_count > scope.max_tokens:
        logger.warning(
            "item_exceeds_max_tokens_truncating",
            item_id=item_id,
            token_count=token_count,
            max_tokens=scope.max_tokens,
        )
        
        # Strategy: Truncate content
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
    
    item = ContextItem(
        id=item_id,
        type=content_type,
        content=content,
        priority=priority,
        owner_scope=scope_name,
        token_count=token_count,
    )
    
    scope.add(item)
```

**Impact:**
- ✅ Система не падает (graceful degradation)
- ⚠️ Content truncated (partial loss of information)

**Alternative (для post-MVP):** Raise exception вместо truncation

**Testing:**
```python
async def test_add_to_scope_item_exceeds_max_tokens():
    fcm = FederatedContextManager(token_counter=token_counter)
    await fcm.create_scope("agent", max_tokens=1000)
    
    huge_content = "x" * 10000  # ~2500 tokens
    
    # Should not raise, truncate instead
    await fcm.add_to_scope("agent", "huge.py", "file_content", huge_content)
    
    scope = fcm.scopes["agent"]
    item = scope.get("huge.py")
    assert item.token_count <= 1000
```

#### Error: share_item когда item не существует

**Scenario:** попытка share несуществующего item

**Behavior:**
```python
async def share_item(
    self,
    source_scope: str,
    target_scope: str,
    item_id: str,
    new_priority: int | None = None,
) -> None:
    """Передать элемент между скоупами."""
    # Validate scopes
    source = self.scopes.get(source_scope)
    if source is None:
        raise ValueError(f"Source scope '{source_scope}' not found")
    
    target = self.scopes.get(target_scope)
    if target is None:
        raise ValueError(f"Target scope '{target_scope}' not found")
    
    # Get item from source
    item = source.get(item_id)
    if item is None:
        logger.error(
            "item_not_found_in_source_scope",
            item_id=item_id,
            source_scope=source_scope,
            available_items=list(source.registry.keys()),
        )
        raise ValueError(
            f"Item '{item_id}' not found in source scope '{source_scope}'. "
            f"Available items: {list(source.registry.keys())}"
        )
    
    # Create copy with new owner_scope
    shared_item = ContextItem(
        id=item.id,
        type=item.type,
        content=item.content,
        priority=new_priority if new_priority is not None else item.priority,
        owner_scope=target_scope,
        last_accessed=item.last_accessed,
        token_count=item.token_count,
    )
    
    target.add(shared_item)
    
    logger.info(
        "item_shared",
        item_id=item_id,
        source_scope=source_scope,
        target_scope=target_scope,
        priority=shared_item.priority,
    )
```

**Rationale:** Programming error → fail fast

**Testing:**
```python
async def test_share_item_not_found():
    fcm = FederatedContextManager()
    await fcm.create_scope("source", max_tokens=4000)
    await fcm.create_scope("target", max_tokens=4000)
    
    with pytest.raises(ValueError, match="Item 'nonexistent.py' not found"):
        await fcm.share_item("source", "target", "nonexistent.py")
```

#### Error: Все элементы priority >= 10 (критические)

**Scenario:** system items превышают max_tokens

**Behavior:**
```python
async def optimize_and_build_payload(
    self,
    scope_name: str,
) -> list[LLMMessage]:
    """Сформировать payload."""
    scope = self.scopes.get(scope_name)
    if scope is None:
        raise ValueError(...)
    
    # Разделение на system и dynamic
    system_items = [
        item for item in scope.registry.values()
        if item.priority >= 10
    ]
    dynamic_items = [
        item for item in scope.registry.values()
        if item.priority < 10
    ]
    
    # Подсчёт system tokens
    system_tokens = sum(item.token_count for item in system_items)
    
    # CRITICAL CHECK: system items must fit
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
            f"Reduce critical items or increase max_tokens. "
            f"Critical items: {[item.id for item in system_items]}"
        )
    
    # Budget для dynamic items
    available_budget = scope.max_tokens - system_tokens
    
    # ... continue with dynamic items ...
```

**Rationale:** Configuration error → fail fast

**Caller должен исправить:** либо уменьшить количество критических элементов, либо увеличить max_tokens

**Testing:**
```python
async def test_critical_items_exceed_budget():
    fcm = FederatedContextManager(token_counter=token_counter)
    await fcm.create_scope("agent", max_tokens=1000)
    
    # Add critical items > budget
    await fcm.add_to_scope("agent", "system_prompt", "system_rules", "x" * 2000, priority=10)
    await fcm.add_to_scope("agent", "critical_file", "file_content", "y" * 3000, priority=10)
    
    with pytest.raises(ValueError, match="Critical items .* exceed scope budget"):
        await fcm.optimize_and_build_payload("agent")
```

---

## 5. Testing Strategy

### 5.1. Unit Tests — все error paths

**Requirement:** 100% coverage для всех error handling блоков

**Examples:**

```python
# test_token_counter.py
def test_tiktoken_counter_encoding_failure():
    """tiktoken.encode raises → fallback to approximate."""
    counter = TiktokenCounter()
    with patch.object(counter._encoding, 'encode', side_effect=RuntimeError(...)):
        result = counter.count("text")
        assert result > 0  # fallback worked

# test_ast_skeletonizer.py
def test_ast_skeletonizer_syntax_error():
    """SyntaxError → return error message + truncated."""
    skeletonizer = PythonASTSkeletonizer()
    invalid = "def foo(:\n    pass"
    result = skeletonizer.skeletonize(invalid, "bad.py")
    assert "ERROR" in result

# test_file_cache.py
def test_file_cache_eviction():
    """Cache full → LRU eviction."""
    cache = InMemoryFileCache(max_size=2)
    cache.set("a", "...")
    cache.set("b", "...")
    cache.set("c", "...")  # evicts a
    assert cache.get("a") is None

# test_compactor.py
@pytest.mark.asyncio
async def test_compactor_skeletonization_failure():
    """Skeletonization failed → use original."""
    mock_skeletonizer = MagicMock()
    mock_skeletonizer.skeletonize.side_effect = RuntimeError(...)
    
    compactor = DefaultContextCompactor(skeletonizer=mock_skeletonizer, ...)
    history = [LLMMessage(role="user", content="code")]
    
    result = await compactor._compact_with_skeleton(history)
    assert result[0].content == "code"  # original used

# test_manager.py
@pytest.mark.asyncio
async def test_fcm_scope_not_found():
    """optimize_and_build_payload для несуществующего scope → ValueError."""
    fcm = FederatedContextManager()
    with pytest.raises(ValueError, match="Scope 'nonexistent' not found"):
        await fcm.optimize_and_build_payload("nonexistent")
```

### 5.2. Integration Tests — cascading failures

**Scenario:** Failure в одном layer не ломает весь pipeline

```python
@pytest.mark.asyncio
async def test_execution_engine_handles_ast_failure():
    """AST parsing failed → компактор fallback → ExecutionEngine продолжает."""
    # Setup: mock skeletonizer to fail
    mock_skeletonizer = MagicMock()
    mock_skeletonizer.skeletonize.side_effect = RuntimeError("AST error")
    
    compactor = DefaultContextCompactor(
        skeletonizer=mock_skeletonizer,
        enable_skeletonization=True,
        ...
    )
    
    fcm = FederatedContextManager(compactor=compactor, ...)
    engine = ExecutionEngine(context_manager=fcm, ...)
    
    # Add file content
    await fcm.create_scope("agent", max_tokens=4000)
    await fcm.add_to_scope("agent", "file.py", "file_content", huge_code)
    
    # build_context should not raise
    context = await engine.build_context(session, prompt, agent_scope="agent")
    
    assert context is not None
    assert len(context.conversation_history) > 0
```

### 5.3. Chaos Engineering Tests (post-MVP)

**Inject failures randomly:**

```python
class ChaosSkeletonizer(CodeSkeletonizer):
    """Randomly fail for chaos testing."""
    
    def __init__(self, wrapped: CodeSkeletonizer, failure_rate: float = 0.1):
        self.wrapped = wrapped
        self.failure_rate = failure_rate
    
    def skeletonize(self, code: str, file_id: str = "", language: str = "python") -> str:
        if random.random() < self.failure_rate:
            raise RuntimeError("Chaos: simulated failure")
        return self.wrapped.skeletonize(code, file_id, language)

@pytest.mark.asyncio
async def test_fcm_chaos():
    """FCM должен выживать при 10% random failures."""
    chaos_skeletonizer = ChaosSkeletonizer(
        PythonASTSkeletonizer(),
        failure_rate=0.1,
    )
    
    fcm = FederatedContextManager(skeletonizer=chaos_skeletonizer, ...)
    
    # Run 100 iterations
    for i in range(100):
        await fcm.add_to_scope("agent", f"file_{i}.py", "file_content", code)
    
    # Should not crash despite 10% failures
    payload = await fcm.optimize_and_build_payload("agent")
    assert payload is not None
```

---

## 6. Monitoring & Alerting

### 6.1. Error Metrics

**Required metrics:**

```python
# Error counters (by type)
metrics.counter("fcm.errors", tags={"layer": "1", "type": "tiktoken_encoding_failed"})
metrics.counter("fcm.errors", tags={"layer": "1", "type": "ast_parse_failed"})
metrics.counter("fcm.errors", tags={"layer": "1", "type": "cache_invalidation_failed"})
metrics.counter("fcm.errors", tags={"layer": "2", "type": "skeletonization_failed"})
metrics.counter("fcm.errors", tags={"layer": "2", "type": "summarization_timeout"})
metrics.counter("fcm.errors", tags={"layer": "3", "type": "scope_not_found"})
metrics.counter("fcm.errors", tags={"layer": "3", "type": "item_truncated"})

# Error rates (per minute)
metrics.gauge("fcm.error_rate", error_count_per_minute)
```

### 6.2. Alerts

```yaml
# alerts.yaml

- alert: FCM_High_Error_Rate
  expr: rate(fcm_errors[5m]) > 0.05  # 5% error rate
  for: 3m
  severity: critical
  action: Investigate logs, consider rollback

- alert: FCM_AST_Parse_Failures_High
  expr: rate(fcm_errors{type="ast_parse_failed"}[5m]) > 0.1
  for: 5m
  severity: warning
  action: Review failing files, check for invalid syntax

- alert: FCM_Summarization_Timeout_High
  expr: rate(fcm_errors{type="summarization_timeout"}[5m]) > 0.05
  for: 5m
  severity: warning
  action: Check LLM latency, consider increasing timeout

- alert: FCM_Cache_Invalidation_Failures
  expr: rate(fcm_errors{type="cache_invalidation_failed"}[1h]) > 10
  for: 10m
  severity: info
  action: Monitor for stale cache issues

- alert: FCM_Item_Truncation_Frequent
  expr: rate(fcm_errors{type="item_truncated"}[1h]) > 50
  for: 15m
  severity: info
  action: Consider increasing max_tokens
```

### 6.3. Dashboard Panels

**Error Rate Panel:**
- Graph: error_rate (per type) over time
- Table: Top 10 error types by count

**Recovery Panel:**
- Gauge: % requests with graceful degradation
- Counter: fallback operations (by type)

**Latency Impact:**
- Histogram: latency comparison (with errors vs without)

---

## 7. Incident Response

### 7.1. Runbook: High Error Rate

**Trigger:** `FCM_High_Error_Rate` alert fires

**Steps:**

1. **Check dashboard:**
   - Какие типы ошибок доминируют?
   - Какой слой affected (1/2/3)?

2. **Review logs:**
   ```bash
   # Last 100 errors with context
   kubectl logs -l app=codelab-server --tail=1000 | grep "fcm.errors"
   ```

3. **Assess severity:**
   - Error rate > 10% → Critical
   - Error rate 5-10% → High
   - Error rate 1-5% → Medium

4. **Actions based on error type:**

   **AST parse failures:**
   - Check: Are all failures in same file/repo?
   - Action: Investigate invalid syntax, update parser

   **Summarization timeouts:**
   - Check: LLM API latency dashboard
   - Action: Increase timeout or reduce summary size

   **Cache invalidation failures:**
   - Check: System memory, disk I/O
   - Action: Restart affected pods if memory issue

5. **If critical:** Execute rollback (см. MIGRATION_PLAN.md § 5)

6. **Post-incident:**
   - File bug report
   - Update EDGE_CASES.md if new edge case discovered

### 7.2. Runbook: Memory Leak

**Trigger:** `FCM_Memory_High` alert + gradual memory increase

**Steps:**

1. **Take heap dump:**
   ```bash
   # Python memory_profiler
   python -m memory_profiler script.py
   ```

2. **Identify leak:**
   - Check: FileContentCache not evicting?
   - Check: AgentContextScope not properly cleaned?

3. **Mitigation:**
   - Restart affected pods
   - Reduce cache max_size temporarily

4. **Fix:**
   - Review lifecycle management
   - Add explicit cleanup in scope destruction

---

## Связанные документы

- [EDGE_CASES.md](./EDGE_CASES.md) — детали edge case handling
- [MIGRATION_PLAN.md](./MIGRATION_PLAN.md) — rollback procedures
- [PERFORMANCE_REQUIREMENTS.md](./PERFORMANCE_REQUIREMENTS.md) — latency SLOs
- [ARCHITECTURE.md](./ARCHITECTURE.md) — архитектура слоёв
