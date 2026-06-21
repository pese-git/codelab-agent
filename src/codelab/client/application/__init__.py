"""Application layer - Use Cases, DTOs, и оркестрация.

Этот слой содержит:
- Use Cases - бизнес-сценарии (CreateSessionUseCase, PromptUseCase и т.д.)
- Data Transfer Objects (DTO) - контракты между слоями
- Application Services - оркестрация use cases

Application слой зависит от Domain слоя,
но не зависит от Infrastructure и Presentation слоев.
"""

from .dto import (
    AudioContent,
    CreateSessionRequest,
    CreateSessionResponse,
    ImageContent,
    LoadSessionRequest,
    LoadSessionResponse,
    ResourceContent,
    ResourceLinkContent,
    SendPromptRequest,
    SendPromptResponse,
)
from .session_coordinator import SessionCoordinator
from .state_machine import StateChange, StateTransitionError, UIState, UIStateMachine
from .use_cases import (
    CreateSessionUseCase,
    InitializeUseCase,
    LoadSessionUseCase,
    SendPromptUseCase,
)

__all__ = [
    # DTOs
    "CreateSessionRequest",
    "CreateSessionResponse",
    "LoadSessionRequest",
    "LoadSessionResponse",
    "SendPromptRequest",
    "SendPromptResponse",
    # Multimodal content DTOs
    "ImageContent",
    "AudioContent",
    "ResourceContent",
    "ResourceLinkContent",
    # Use Cases
    "CreateSessionUseCase",
    "LoadSessionUseCase",
    "SendPromptUseCase",
    "InitializeUseCase",
    # Coordinators
    "SessionCoordinator",
    # State Machine
    "UIState",
    "UIStateMachine",
    "StateChange",
    "StateTransitionError",
]
