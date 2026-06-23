"""Domain layer - бизнес-логика и интерфейсы сущностей.

Этот слой содержит:
- Entities (Session, Permission, ClientCapabilities и т.д.)
- Content Blocks (TextContent, ImageContent, AudioContent и т.д.)
- Prompt Capabilities (PromptCapabilities)
- Content Builder (ContentBuilder)
- Repositories интерфейсы (SessionRepository и т.д.)
- Domain Services интерфейсы (TransportService и т.д.)

Domain слой не зависит от других слоев архитектуры.
"""

from .content_blocks import (
    AudioContent,
    ContentBlock,
    ImageContent,
    ResourceContent,
    ResourceLink,
    ResourceLinkContent,
    TextContent,
    content_blocks_to_dicts,
)
from .content_builder import ContentBuilder
from .entities import ClientCapabilities, Permission, Session
from .prompt_capabilities import PromptCapabilities, UnsupportedContentError
from .repositories import SessionRepository
from .services import TransportService

__all__ = [
    # Entities
    "ClientCapabilities",
    "Session",
    "Permission",
    # Content Blocks
    "ContentBlock",
    "TextContent",
    "ImageContent",
    "AudioContent",
    "ResourceContent",
    "ResourceLinkContent",
    "ResourceLink",
    "content_blocks_to_dicts",
    # Prompt Capabilities
    "PromptCapabilities",
    "UnsupportedContentError",
    # Content Builder
    "ContentBuilder",
    # Repositories
    "SessionRepository",
    # Services
    "TransportService",
]
