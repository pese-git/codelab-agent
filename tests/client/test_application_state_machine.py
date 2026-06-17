"""Тесты для State Machine."""

from __future__ import annotations

import pytest

from codelab.client.application import (
    StateChange,
    StateTransitionError,
    UIState,
    UIStateMachine,
)


class TestUIState:
    """Тесты для UIState enum."""
    
    def test_ui_state_values(self) -> None:
        """Тест что все состояния имеют правильные значения."""
        assert UIState.INITIALIZING.value == "initializing"
        assert UIState.READY.value == "ready"
        assert UIState.PROCESSING_PROMPT.value == "processing_prompt"
        assert UIState.WAITING_PERMISSION.value == "waiting_permission"
        assert UIState.CANCELLING.value == "cancelling"
        assert UIState.RECONNECTING.value == "reconnecting"
        assert UIState.ERROR.value == "error"


class TestUIStateMachine:
    """Тесты для UIStateMachine."""
    
    def test_initial_state(self) -> None:
        """Тест начального состояния."""
        sm = UIStateMachine()
        assert sm.current_state == UIState.INITIALIZING
    
    def test_custom_initial_state(self) -> None:
        """Тест установки пользовательского начального состояния."""
        sm = UIStateMachine(initial_state=UIState.READY)
        assert sm.current_state == UIState.READY
    
    def test_valid_transition(self) -> None:
        """Тест валидного перехода."""
        sm = UIStateMachine(initial_state=UIState.READY)
        assert sm.can_transition(UIState.PROCESSING_PROMPT)
        
        state_change = sm.transition(UIState.PROCESSING_PROMPT)
        assert sm.current_state == UIState.PROCESSING_PROMPT
        assert state_change.from_state == UIState.READY
        assert state_change.to_state == UIState.PROCESSING_PROMPT
    
    def test_invalid_transition(self) -> None:
        """Тест что невалидный переход выбрасывает исключение."""
        sm = UIStateMachine(initial_state=UIState.INITIALIZING)
        
        # Из INITIALIZING нельзя перейти в PROCESSING_PROMPT
        assert not sm.can_transition(UIState.PROCESSING_PROMPT)
        
        with pytest.raises(StateTransitionError):
            sm.transition(UIState.PROCESSING_PROMPT)
    
    def test_transition_with_reason(self) -> None:
        """Тест переход с причиной."""
        sm = UIStateMachine(initial_state=UIState.READY)
        reason = "User started typing"
        
        state_change = sm.transition(UIState.PROCESSING_PROMPT, reason=reason)
        assert state_change.reason == reason
    
    def test_transition_with_metadata(self) -> None:
        """Тест переход с метаданными."""
        sm = UIStateMachine(initial_state=UIState.READY)
        metadata = {"session_id": "123", "prompt_length": 50}
        
        state_change = sm.transition(
            UIState.PROCESSING_PROMPT,
            metadata=metadata,
        )
        assert state_change.metadata == metadata
    
    def test_transition_same_state_not_allowed(self) -> None:
        """Тест что переход в то же состояние не допускается."""
        sm = UIStateMachine(initial_state=UIState.READY)
        
        assert not sm.can_transition(UIState.READY)
        
        with pytest.raises(StateTransitionError):
            sm.transition(UIState.READY)
    
    def test_state_change_listener(self) -> None:
        """Тест что слушатель получает уведомления об изменениях."""
        sm = UIStateMachine(initial_state=UIState.READY)
        
        changes: list[StateChange] = []
        
        def listener(change: StateChange) -> None:
            changes.append(change)
        
        sm.on_state_change(listener)
        sm.transition(UIState.PROCESSING_PROMPT)
        
        assert len(changes) == 1
        assert changes[0].to_state == UIState.PROCESSING_PROMPT
    
    def test_multiple_listeners(self) -> None:
        """Тест что несколько слушателей получают уведомления."""
        sm = UIStateMachine(initial_state=UIState.READY)
        
        changes1: list[StateChange] = []
        changes2: list[StateChange] = []
        
        def listener1(change: StateChange) -> None:
            changes1.append(change)
        
        def listener2(change: StateChange) -> None:
            changes2.append(change)
        
        sm.on_state_change(listener1)
        sm.on_state_change(listener2)
        sm.transition(UIState.PROCESSING_PROMPT)
        
        assert len(changes1) == 1
        assert len(changes2) == 1
    
    def test_remove_listener(self) -> None:
        """Тест удаления слушателя."""
        sm = UIStateMachine(initial_state=UIState.READY)
        
        changes: list[StateChange] = []
        
        def listener(change: StateChange) -> None:
            changes.append(change)
        
        sm.on_state_change(listener)
        sm.remove_listener(listener)
        sm.transition(UIState.PROCESSING_PROMPT)
        
        assert len(changes) == 0
    
    def test_reset(self) -> None:
        """Тест сброса State Machine."""
        sm = UIStateMachine(initial_state=UIState.INITIALIZING)
        sm.transition(UIState.READY)
        
        assert sm.current_state == UIState.READY
        
        sm.reset()
        assert sm.current_state == UIState.INITIALIZING
    
    def test_reset_custom_state(self) -> None:
        """Тест сброса в пользовательское состояние."""
        sm = UIStateMachine(initial_state=UIState.INITIALIZING)
        sm.transition(UIState.READY)
        
        sm.reset(UIState.ERROR)
        assert sm.current_state == UIState.ERROR
    
    def test_complex_transition_sequence(self) -> None:
        """Тест сложной последовательности переходов."""
        sm = UIStateMachine(initial_state=UIState.INITIALIZING)
        
        # INITIALIZING -> READY
        sm.transition(UIState.READY)
        assert sm.current_state == UIState.READY
        
        # READY -> PROCESSING_PROMPT
        sm.transition(UIState.PROCESSING_PROMPT)
        assert sm.current_state == UIState.PROCESSING_PROMPT
        
        # PROCESSING_PROMPT -> WAITING_PERMISSION
        sm.transition(UIState.WAITING_PERMISSION)
        assert sm.current_state == UIState.WAITING_PERMISSION
        
        # WAITING_PERMISSION -> READY
        sm.transition(UIState.READY)
        assert sm.current_state == UIState.READY
    
    def test_error_state_recovery(self) -> None:
        """Тест восстановления из ERROR состояния."""
        sm = UIStateMachine(initial_state=UIState.READY)
        
        sm.transition(UIState.ERROR)
        assert sm.current_state == UIState.ERROR
        
        # Из ERROR можно перейти в RECONNECTING
        sm.transition(UIState.RECONNECTING)
        assert sm.current_state == UIState.RECONNECTING
        
        # И затем в READY
        sm.transition(UIState.READY)
        assert sm.current_state == UIState.READY
