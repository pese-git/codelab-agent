# spec: remove-legacy-architecture

## ADDED requirements

### ModelResolver (standalone)
- The system SHALL provide `ModelResolver` as a standalone DI component, not bound to `AgentOrchestrator`.
- `ModelResolver` SHALL be created in `RegistryProvider` or a dedicated provider.
- `ACPProtocol` SHALL accept `model_resolver: ModelResolver | None` in its constructor.
- `ACPProtocol._get_default_model()` SHALL use `self._model_resolver` instead of `agent_orchestrator.config`.
- `ACPProtocol._handle_set_config_option()` SHALL use `self._model_resolver` for cache invalidation.

### LLMAdapter.cancel_prompt()
- `LLMAdapter` SHALL provide `cancel_prompt(session_id: str) -> None` method.
- `LLMAgent` Protocol SHALL include `cancel_prompt(session_id)` in its interface.
- `ACPProtocol` SHALL accept `llm_adapter: LLMAdapter | None` in its constructor.
- `ACPProtocol._handle_session_cancel()` SHALL call `llm_adapter.cancel_prompt(session_id)` instead of `agent_orchestrator.cancel_prompt(session_id)`.

## REMOVED requirements

### AgentOrchestrator
- The system SHALL NOT provide `AgentOrchestrator` class.
- `AgentOrchestrator` SHALL NOT be imported or referenced anywhere in the codebase.
- `AgentProvider` DI provider SHALL NOT exist.

### NaiveAgent
- The system SHALL NOT provide `NaiveAgent` class.
- `NaiveAgent` SHALL NOT be imported or referenced anywhere in the codebase.

### LegacyCallStrategy
- The system SHALL NOT provide `LegacyCallStrategy` class.
- `LegacyCallStrategy` SHALL NOT be imported or referenced anywhere in the codebase.
- `LLMLoopStage` SHALL NOT fallback to `LegacyCallStrategy` when `StrategyDispatcher` is unavailable.

## MODIFIED requirements

### PromptOrchestrator
- `PromptOrchestrator.handle_prompt()` SHALL NOT accept `agent_orchestrator` parameter.
- `PromptOrchestrator.execute_pending_tool()` SHALL NOT accept `agent_orchestrator` parameter.
- `PromptContext.meta` SHALL NOT contain `agent_orchestrator` key.

### LLMLoopStage
- `LLMLoopStage` SHALL require `strategy_dispatcher` — fallback to legacy path SHALL be removed.
- `LLMLoopStage.execute_pending_tool()` SHALL NOT accept `agent_orchestrator` parameter.
- `LLMLoopStage` SHALL raise `ValueError` when `strategy_dispatcher` is not configured.

### ACPProtocol
- `ACPProtocol.__init__()` SHALL NOT accept `agent_orchestrator` parameter.
- `ACPProtocol.__init__()` SHALL accept `model_resolver: ModelResolver | None` parameter.
- `ACPProtocol.__init__()` SHALL accept `llm_adapter: LLMAdapter | None` parameter.

### DI Container
- `make_container()` SHALL NOT include `AgentProvider`.
- `RequestProvider.get_acp_protocol()` SHALL NOT accept `agent_orchestrator` parameter.
- The system SHALL provide `ModelResolver` through DI.
- The system SHALL provide `LLMAdapter` through DI (via `ExecutionEngine` or `AgentFactory`).

### Exports
- `codelab.server.agent.__init__` SHALL NOT export `NaiveAgent` or `AgentOrchestrator`.
- `codelab.server.agent.strategies.__init__` SHALL NOT export `LegacyCallStrategy`.
