"""Компоненты пользовательского интерфейса TUI.

Фаза 1 (Core Layout):
- MainLayout: главный контейнер с трехколоночной структурой
- StyledContainer, Card: универсальные контейнеры
- CollapsiblePanel, AccordionPanel: сворачиваемые панели
- HeaderBar, FooterBar: улучшенные header/footer

Фаза 2 (Session Components):
- MarkdownViewer, InlineMarkdown, CodeBlock: рендеринг Markdown
- StreamingText, TypewriterText, ThinkingIndicator: streaming text
- MessageBubble, Avatar, MessageRole: отображение сообщений
- MessageList, DateSeparator: список сообщений
- SessionTurn, TurnStatus, TurnData: turn компоненты

Фаза 3 (Tool Components):
- ActionButton, IconButton: стилизованные кнопки
- ActionBar: панель с кнопками действий
- PermissionBadge: badge статуса разрешения
- PermissionRequest: виджет запроса разрешения
- ToolCallCard: карточка tool call
- ToolCallList: список tool calls
- FileChangePreview, DiffLine: предпросмотр изменений файла

Фаза 4 (Advanced Features):
- Toast, ToastContainer, ToastType, ToastData: всплывающие уведомления
- Tab, TabBar, TabPanel, TabbedContainer, TabData: компоненты табов
- SearchInput: поле поиска с debounce
- ProgressBar, ProgressVariant: индикатор прогресса
- Spinner, LoadingIndicator, SpinnerSize, SpinnerVariant: индикаторы загрузки
- ContextMenu, ContextMenuScreen, MenuItem, MenuSeparator, MenuGroup: контекстное меню
- TerminalPanel, TerminalSession, TerminalOutput, TerminalToolbar: панель терминала
"""

from .action_bar import ActionBar
from .action_button import ActionButton, ButtonVariant, IconButton
from .chat_view import ChatView
from .chat_view_permission_manager import ChatViewPermissionManager, PermissionWidgetType
from .collapsible_panel import AccordionGroup
from .command_palette import Command, CommandCategory, CommandItem, CommandPalette
from .config_option_selector import ConfigOptionSelectorModal
from .container import Card, ContainerVariant, StyledContainer
from .context_menu import (
    ContextMenu,
    ContextMenuItem,
    ContextMenuScreen,
    MenuGroup,
    MenuItem,
    MenuSeparator,
)
from .file_change_preview import DiffLine, FileChangePreview
from .file_change_preview_modal import FileChangePreviewModal
from .file_tree import FileTree
from .file_viewer import FileViewerModal
from .footer import AgentStatus, FooterBar
from .header import HeaderBar
from .help_modal import HelpModal
from .inline_permission_widget import InlinePermissionWidget
from .inline_selector import InlineSelector
from .keyboard_manager import (
    CATEGORY_NAMES,
    DEFAULT_BINDINGS,
    HotkeyBinding,
    HotkeyCategory,
    HotkeyGroup,
    KeyboardManager,
    get_keyboard_manager,
    set_keyboard_manager,
)
from .main_layout import LayoutConfig, MainLayout
from .markdown import CodeBlock, InlineMarkdown, MarkdownViewer
from .message_bubble import Avatar, MessageBubble, MessageRole
from .message_list import DateSeparator, MessageList
from .model_selector import ModelItem, ModelSelectorModal
from .panel import AccordionPanel, CollapsiblePanel
from .permission_badge import PermissionBadge, PermissionStatus
from .permission_modal import PermissionModal
from .permission_request import PermissionRequest, PermissionType
from .plan_panel import PlanPanel
from .progress import ProgressBar, ProgressVariant
from .prompt_input import PromptInput
from .quick_actions_bar import QuickActionsBar
from .search_input import SearchInput
from .session_turn import SessionTurn, TurnData, TurnStatus
from .sidebar import Sidebar
from .spinner import LoadingIndicator, Spinner, SpinnerSize, SpinnerVariant
from .status_line import CompactStatusLine, StatusIndicator, StatusLine, StatusMode
from .streaming_text import StreamingText, ThinkingIndicator, TypewriterText
from .tabs import Tab, TabBar, TabbedContainer, TabData, TabPanel
from .terminal_log_modal import TerminalLogModal
from .terminal_output import (
    TerminalOutputContent,
    TerminalOutputPanel,
    TerminalOutputToolbar,
)
from .terminal_panel import TerminalOutput, TerminalPanel, TerminalSession, TerminalToolbar
from .toast import Toast, ToastContainer, ToastData, ToastType
from .tool_call_card import ToolCallCard, ToolCallStatus
from .tool_call_list import ToolCallList
from .tool_panel import ToolPanel

__all__ = [
    # Layout компоненты (Фаза 1)
    "MainLayout",
    "LayoutConfig",
    "StyledContainer",
    "ContainerVariant",
    "Card",
    "CollapsiblePanel",
    "AccordionPanel",
    "AccordionGroup",
    # Header/Footer
    "HeaderBar",
    "FooterBar",
    "AgentStatus",
    # Sidebar
    "Sidebar",
    # Chat
    "ChatView",
    "ChatViewPermissionManager",
    "PermissionWidgetType",
    # Files
    "FileTree",
    "FileViewerModal",
    # Input
    "PromptInput",
    # Modals
    "HelpModal",
    "PermissionModal",
    "InlinePermissionWidget",
    # Panels
    "PlanPanel",
    "TerminalLogModal",
    "TerminalOutputContent",
    "TerminalOutputPanel",
    "TerminalOutputToolbar",
    "ToolPanel",
    # Фаза 2: Markdown компоненты
    "MarkdownViewer",
    "InlineMarkdown",
    "CodeBlock",
    # Фаза 2: Streaming компоненты
    "StreamingText",
    "TypewriterText",
    "ThinkingIndicator",
    # Фаза 2: Message компоненты
    "Avatar",
    "MessageBubble",
    "MessageRole",
    "MessageList",
    "DateSeparator",
    # Фаза 2: Session Turn компоненты
    "SessionTurn",
    "TurnStatus",
    "TurnData",
    # Фаза 3: Tool компоненты
    "ActionButton",
    "IconButton",
    "ButtonVariant",
    "ActionBar",
    "PermissionBadge",
    "PermissionStatus",
    "PermissionRequest",
    "PermissionType",
    "ToolCallCard",
    "ToolCallStatus",
    "ToolCallList",
    "FileChangePreview",
    "FileChangePreviewModal",
    "DiffLine",
    # Фаза 4: Advanced компоненты
    "Toast",
    "ToastContainer",
    "ToastType",
    "ToastData",
    "Tab",
    "TabBar",
    "TabPanel",
    "TabbedContainer",
    "TabData",
    "SearchInput",
    "ProgressBar",
    "ProgressVariant",
    "Spinner",
    "LoadingIndicator",
    "SpinnerSize",
    "SpinnerVariant",
    "ContextMenu",
    "ContextMenuItem",
    "ContextMenuScreen",
    "MenuItem",
    "MenuSeparator",
    "MenuGroup",
    "TerminalPanel",
    "TerminalSession",
    "TerminalOutput",
    "TerminalToolbar",
    # Фаза 5: Polish компоненты
    "KeyboardManager",
    "HotkeyBinding",
    "HotkeyCategory",
    "HotkeyGroup",
    "CATEGORY_NAMES",
    "DEFAULT_BINDINGS",
    "get_keyboard_manager",
    "set_keyboard_manager",
    "CommandPalette",
    "Command",
    "CommandCategory",
    "CommandItem",
    "ModelSelectorModal",
    "ModelItem",
    "ConfigOptionSelectorModal",
    "InlineSelector",
    "StatusLine",
    "CompactStatusLine",
    "StatusMode",
    "StatusIndicator",
    # Панель быстрых действий
    "QuickActionsBar",
]
