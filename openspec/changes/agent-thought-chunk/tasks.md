## 1. Server Foundation (LLM Models)

- [ ] 1.1 Add `reasoning: str | None = None` field to `CompletionResponse` in `src/codelab/server/llm/models.py`
- [ ] 1.2 Add unit tests for `CompletionResponse` with reasoning field (presence, absence, empty string)
- [ ] 1.3 Run `make check` to verify no type/lint errors

## 2. Server Foundation (ReplayManager)

- [ ] 2.1 Add `"agent_thought_chunk"` to `_REPLAYABLE_UPDATE_TYPES` frozenset in `src/codelab/server/protocol/handlers/replay_manager.py`
- [ ] 2.2 Implement `save_thought_chunk(session, content)` method in `ReplayManager`
- [ ] 2.3 Add unit tests for `save_thought_chunk()` (save, replay, order preservation)
- [ ] 2.4 Run `make check` to verify no type/lint errors

## 3. Server Foundation (AgentLoop)

- [ ] 3.1 Add `_build_thought_notification(session_id, reasoning)` helper method to `AgentLoop` in `src/codelab/server/protocol/handlers/pipeline/stages/agent_loop.py`
- [ ] 3.2 Add reasoning emission logic in `AgentLoop.run()` — emit `agent_thought_chunk` before `agent_message_chunk` when `response.reasoning` is not None and not empty
- [ ] 3.3 Add reasoning emission in `AgentLoop.resume_after_permission()` if applicable
- [ ] 3.4 Add unit tests for thought notification emission (with reasoning, without reasoning, empty reasoning, order)
- [ ] 3.5 Run `make check` to verify no type/lint errors

## 4. Server Foundation (StrategyDispatcher)

- [ ] 4.1 Add reasoning emission logic in `src/codelab/server/agent/strategies/dispatcher.py` — emit `agent_thought_chunk` when response has reasoning
- [ ] 4.2 Add unit tests for dispatcher thought emission
- [ ] 4.3 Run `make check` to verify no type/lint errors

## 5. LLM Provider Integration (Anthropic)

- [ ] 5.1 Implement thinking extraction in `src/codelab/server/llm/providers/anthropic.py` — extract `content[].type == "thinking"` blocks from non-streaming responses
- [ ] 5.2 Implement thinking extraction for Anthropic streaming responses — aggregate thinking chunks
- [ ] 5.3 Add unit tests for Anthropic thinking extraction (with thinking, without thinking, streaming)
- [ ] 5.4 Run `make check` to verify no type/lint errors

## 6. LLM Provider Integration (OpenAI)

- [ ] 6.1 Implement reasoning extraction in `src/codelab/server/llm/providers/openai.py` — extract `choices[].message.reasoning_content`
- [ ] 6.2 Implement reasoning extraction for OpenAI streaming responses
- [ ] 6.3 Add unit tests for OpenAI reasoning extraction
- [ ] 6.4 Run `make check` to verify no type/lint errors

## 7. LLM Provider Integration (OpenRouter)

- [ ] 7.1 Implement reasoning extraction in `src/codelab/server/llm/providers/openrouter.py` — extract reasoning field
- [ ] 7.2 Add unit tests for OpenRouter reasoning extraction
- [ ] 7.3 Run `make check` to verify no type/lint errors

## 8. Client State (ChatSessionState)

- [ ] 8.1 Add `thinking_text: str = ""` and `is_thinking_streaming: bool = False` fields to `ChatSessionState` in `src/codelab/client/presentation/chat/chat_session_state.py`
- [ ] 8.2 Implement `append_streaming_thought(text)` method
- [ ] 8.3 Implement `finalize_thinking()` method
- [ ] 8.4 Update `clear()` method to reset thinking fields
- [ ] 8.5 Add unit tests for thinking state methods
- [ ] 8.6 Run `make check` to verify no type/lint errors

## 9. Client Handler (ThoughtChunkHandler)

- [ ] 9.1 Create `ThoughtChunkHandler` class in `src/codelab/client/presentation/chat/handlers/thought_chunk_handler.py` implementing `SessionUpdateHandler` protocol
- [ ] 9.2 Implement `can_handle(update_type)` — return True for `"agent_thought_chunk"`
- [ ] 9.3 Implement `handle(update_data, context)` — extract text, call `append_streaming_thought`, call `sync_thinking`
- [ ] 9.4 Add unit tests for `ThoughtChunkHandler` (can_handle, handle with text, handle with empty text)
- [ ] 9.5 Run `make check` to verify no type/lint errors

## 10. Client Sink (ChatUpdateSink)

- [ ] 10.1 Add `sync_thinking(session_id: str, text: str, is_streaming: bool) -> None` method to `ChatUpdateSink` protocol in `src/codelab/client/presentation/chat/contracts.py`
- [ ] 10.2 Implement `sync_thinking()` in `ChatViewModel` (or appropriate sink implementation)
- [ ] 10.3 Add unit tests for sink implementation
- [ ] 10.4 Run `make check` to verify no type/lint errors

## 11. Client Dispatcher Integration

- [ ] 11.1 Register `ThoughtChunkHandler` in `SessionUpdateDispatcher` — add to handlers list and `_handler_map` in `src/codelab/client/presentation/chat/dispatcher/session_update_dispatcher.py`
- [ ] 11.2 Register `ThoughtChunkHandler` in DI container (`ViewModelProvider`) with `Scope.APP`
- [ ] 11.3 Add unit tests for dispatcher routing of `agent_thought_chunk`
- [ ] 11.4 Run `make check` to verify no type/lint errors

## 12. Client MessageChunkHandler Integration

- [ ] 12.1 Update `MessageChunkHandler` in `src/codelab/client/presentation/chat/handlers/message_chunk_handler.py` to finalize thinking when receiving `agent_message_chunk`
- [ ] 12.2 Add logic: if `context.state.is_thinking_streaming` is True, call `finalize_thinking()` and `sync_thinking()` with empty text
- [ ] 12.3 Add unit tests for thinking finalization on first message chunk
- [ ] 12.4 Run `make check` to verify no type/lint errors

## 13. TUI Widget (ThoughtPanel)

- [ ] 13.1 Create `ThoughtPanel` class in `src/codelab/client/tui/components/thought_panel.py` inheriting from `CollapsiblePanel`
- [ ] 13.2 Implement `update_content(text)` method — update Markdown content, auto-expand if collapsed
- [ ] 13.3 Implement `collapse_after_answer()` method — collapse panel
- [ ] 13.4 Add default styling for `ThoughtPanel` (distinct from message bubbles)
- [ ] 13.5 Add unit tests for `ThoughtPanel` (creation, update, collapse)
- [ ] 13.6 Run `make check` to verify no type/lint errors

## 14. TUI Integration (ChatView)

- [ ] 14.1 Integrate `ThoughtPanel` into `ChatView` — mount before message area
- [ ] 14.2 Connect `ThoughtPanel` to `ChatViewModel` thinking updates
- [ ] 14.3 Implement auto-collapse when answer streaming starts
- [ ] 14.4 Add integration tests for ChatView + ThoughtPanel
- [ ] 14.5 Run `make check` to verify no type/lint errors

## 15. Integration Tests

- [ ] 15.1 Add end-to-end test: LLM response with reasoning → server emits thought chunk → client handles → state updates
- [ ] 15.2 Add session load test: thought chunks replayed in correct order
- [ ] 15.3 Add cancel test: thinking finalized on session/cancel
- [ ] 15.4 Run `make check` to verify all tests pass

## 16. Documentation and Cleanup

- [ ] 16.1 Update `CHANGELOG.md` with agent_thought_chunk feature
- [ ] 16.2 Verify all specs in `openspec/specs/` are up to date (run `openspec validate agent-thought-chunk`)
- [ ] 16.3 Run full test suite: `make check`
- [ ] 16.4 Create PR with all changes
