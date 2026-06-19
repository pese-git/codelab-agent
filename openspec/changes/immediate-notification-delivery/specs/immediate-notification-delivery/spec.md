# Spec: immediate-notification-delivery

## ДОБАВЛЕННЫЕ Требования

### Требование: AgentLoop принимает notification_callback

`AgentLoop.__init__()` ДОЛЖЕН принимать опциональный параметр `notification_callback`:
```python
def __init__(
    self,
    # ... existing params ...
    notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
) -> None:
    self._notification_callback = notification_callback
```

Параметр ДОЛЖЕН быть опциональным для backward compatibility.

### Требование: AgentLoop имеет метод _send_notification_immediately

`AgentLoop` ДОЛЖЕН иметь метод `_send_notification_immediately()`:
```python
async def _send_notification_immediately(self, notification: ACPMessage) -> None:
    """Отправить notification немедленно через callback если он задан."""
    if self._notification_callback is not None:
        try:
            await self._notification_callback(notification)
        except Exception as e:
            logger.warning(
                "notification_callback_failed",
                notification_method=notification.method,
                error=str(e),
                exc_info=True,
            )
```

Метод ДОЛЖЕН:
- Проверять наличие callback перед вызовом
- Обрабатывать ошибки gracefully (логировать warning, не прерывать выполнение)
- Позволять loop продолжить работу при ошибке callback

### Требование: Agent response notifications отправляются немедленно

`AgentLoop.run()` ДОЛЖЕН вызывать `_send_notification_immediately()` для agent response notifications:
```python
if agent_text:
    notification = self._build_agent_response_notification(session_id, agent_text)
    notifications.append(notification)
    await self._send_notification_immediately(notification)  # NEW
```

### Требование: Plan notifications отправляются немедленно

`AgentLoop` ДОЛЖЕН вызывать `_send_notification_immediately()` для plan notifications:
- В `run()` методе (строка ~268)
- В `_process_tool_calls()` методе (строка ~761)

```python
plan_notification = self._plan_builder.build_plan_notification(session_id, validated_plan)
notifications.append(plan_notification)
await self._send_notification_immediately(plan_notification)  # NEW
```

### Требование: Tool call notifications отправляются немедленно

`AgentLoop._process_tool_calls()` ДОЛЖЕН вызывать `_send_notification_immediately()` для tool call notifications:
```python
tool_call_notification = self._tool_call_handler.build_tool_call_notification(
    session_id=session_id,
    tool_call_id=tool_call_id,
    title=acp_tool_name,
    kind=tool_kind,
)
notifications.append(tool_call_notification)
await self._send_notification_immediately(tool_call_notification)  # NEW
```

### Требование: Permission request notifications отправляются немедленно

`AgentLoop._process_tool_calls()` ДОЛЖЕН вызывать `_send_notification_immediately()` для permission request notifications:
```python
permission_msg = self._permission_manager.build_permission_request(...)
notifications.append(permission_msg)
await self._send_notification_immediately(permission_msg)  # NEW
```

### Требование: Tool execution status notifications отправляются немедленно (КРИТИЧНО)

`AgentLoop._process_tool_calls()` ДОЛЖЕН вызывать `_send_notification_immediately()` для tool execution status notifications:

**"in_progress" status:**
```python
in_progress_notification = self._tool_call_handler.build_tool_update_notification(
    session_id=session_id,
    tool_call_id=tool_call_id,
    status="in_progress",
)
notifications.append(in_progress_notification)
await self._send_notification_immediately(in_progress_notification)  # NEW
```

**"completed/failed" status с content (КРИТИЧНО для terminal embedding):**
```python
tool_update_notification = self._tool_call_handler.build_tool_update_notification(
    session_id=session_id,
    tool_call_id=tool_call_id,
    status=status,
    content=notification_content,  # Может содержать terminal embedding!
)
notifications.append(tool_update_notification)
await self._send_notification_immediately(tool_update_notification)  # NEW — КРИТИЧНО!
```

### Требование: Tool rejection notifications отправляются немедленно

`AgentLoop._process_tool_calls()` ДОЛЖЕН вызывать `_send_notification_immediately()` для tool rejection notifications:
```python
rejection_notification = self._tool_call_handler.build_tool_update_notification(
    session_id=session_id,
    tool_call_id=tool_call_id,
    status="failed",
    content=rejection_content,
)
notifications.append(rejection_notification)
await self._send_notification_immediately(rejection_notification)  # NEW
```

### Требование: Error notifications отправляются немедленно

`AgentLoop.run()` ДОЛЖЕН вызывать `_send_notification_immediately()` для error notifications:
```python
error_notification = self._build_error_notification(session_id, str(e))
notifications.append(error_notification)
await self._send_notification_immediately(error_notification)  # NEW
```

### Требование: LLMLoopStage пробрасывает notification_callback

`LLMLoopStage.execute_pending_tool()` ДОЛЖЕН принимать и пробрасывать `notification_callback`:
```python
async def execute_pending_tool(
    self,
    session: SessionState,
    session_id: str,
    tool_call_id: str,
    mcp_manager: Any | None = None,
    notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,  # NEW
) -> LLMLoopResult:
    # ...
    self._agent_loop = AgentLoop(
        # ... existing params ...
        notification_callback=notification_callback,  # NEW
    )
```

### Требование: PromptOrchestrator пробрасывает notification_callback

`PromptOrchestrator.execute_pending_tool()` ДОЛЖЕН принимать и пробрасывать `notification_callback`:
```python
async def execute_pending_tool(
    self,
    session: SessionState,
    session_id: str,
    tool_call_id: str,
    mcp_manager: Any | None = None,
    notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,  # NEW
) -> LLMLoopResult:
    return await self._llm_loop_stage.execute_pending_tool(
        # ... existing params ...
        notification_callback=notification_callback,  # NEW
    )
```

### Требование: ProtocolCore передаёт self._send_message как callback

`ProtocolCore.execute_pending_tool()` ДОЛЖЕН передавать `self._send_message` как `notification_callback`:
```python
llm_result = await orchestrator.execute_pending_tool(
    session=session,
    session_id=session_id,
    tool_call_id=tool_call_id,
    mcp_manager=mcp_manager,
    notification_callback=self._send_message,  # NEW — КЛЮЧЕВОЕ ИЗМЕНЕНИЕ!
)
```

### Требование: Terminal embedding notification доставляется < 100ms

Система ДОЛЖНА обеспечивать доставку terminal embedding notification клиенту в течение 100ms после создания:
```python
# Integration тест
start_time = time.time()
# Trigger terminal/create
# ...
latency_ms = (notification_timestamp - start_time) * 1000
assert latency_ms < 100, f"Terminal notification latency {latency_ms}ms > 100ms"
```

### Требование: Backward compatibility без callback

Система ДОЛЖНА поддерживать работу без `notification_callback`:
- Если callback не задан, notifications только накапливаются в списке
- Существующий код работает без изменений
- Batch mode отправки сохраняется

### Требование: Unit тесты для AgentLoop callback

Система ДОЛЖНА предоставлять unit тесты:
- Тест: callback не вызывается если None
- Тест: callback вызывается для agent response notification
- Тест: callback вызывается для tool call notification
- Тест: callback вызывается для tool update notification с content
- Тест: ошибка в callback не прерывает AgentLoop
- Тест: warning логируется при ошибке callback
- Тест: notification по-прежнему в списке при ошибке callback

### Требование: Unit тесты для immediate sending

Система ДОЛЖНА предоставлять unit тесты:
- Тест: agent response notification отправляется немедленно
- Тест: tool call notification отправляется немедленно
- Тест: tool update с terminal content отправляется немедленно
- Тест: permission request notification отправляется немедленно
- Тест: error notification отправляется немедленно

### Требование: Unit тесты для проброса callback

Система ДОЛЖНА предоставлять unit тесты:
- Тест: LLMLoopStage пробрасывает callback в AgentLoop
- Тест: PromptOrchestrator пробрасывает callback в LLMLoopStage
- Тест: ProtocolCore передаёт self._send_message как callback

### Требование: Integration тест terminal embedding

Система ДОЛЖНА предоставлять integration тест:
- Тест: terminal notification доставляется < 100ms
- Тест: notification содержит terminalId
- Тест: notification содержит terminal content
- Тест: клиент может начать отображение live output

### Требование: Performance benchmark

Система ДОЛЖНА предоставлять performance benchmark:
- Тест: измерить latency для 100 notifications
- Тест: average latency < 50ms
- Тест: P95 latency < 100ms

### Требование: Обратная совместимость

Система ДОЛЖНА сохранять полную обратную совместимость:
- Существующие тесты проходят без изменений
- Без callback notifications накапливаются как раньше
- Batch mode отправки работает если callback не задан
- Публичные контракты не изменяются
