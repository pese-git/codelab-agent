"""Тесты для компонентов Session (Фаза 2 миграции UI).

Тестируем:
- Markdown компоненты: MarkdownViewer, InlineMarkdown, CodeBlock
- Streaming компоненты: StreamingText, TypewriterText, ThinkingIndicator
- Message компоненты: MessageBubble, Avatar, MessageRole
- MessageList компонент
- SessionTurn компонент
"""

from datetime import datetime


class TestInlineMarkdown:
    """Тесты для InlineMarkdown компонента.
    
    InlineMarkdown теперь наследуется от textual.widgets.Markdown
    и парсит Markdown напрямую без конвертации в Rich markup.
    """
    
    def test_bold_preserved(self) -> None:
        """**bold** Markdown синтаксис сохраняется для парсинга."""
        from codelab.client.tui.components.markdown import InlineMarkdown
        
        md = InlineMarkdown("**bold text**")
        assert md.raw_content == "**bold text**"
    
    def test_italic_preserved(self) -> None:
        """*italic* Markdown синтаксис сохраняется для парсинга."""
        from codelab.client.tui.components.markdown import InlineMarkdown
        
        md = InlineMarkdown("*italic text*")
        assert md.raw_content == "*italic text*"
    
    def test_inline_code_preserved(self) -> None:
        """`code` Markdown синтаксис сохраняется."""
        from codelab.client.tui.components.markdown import InlineMarkdown
        
        md = InlineMarkdown("`code`")
        assert md.raw_content == "`code`"
    
    def test_link_preserved(self) -> None:
        """[text](url) Markdown синтаксис сохраняется."""
        from codelab.client.tui.components.markdown import InlineMarkdown

        md = InlineMarkdown("[link](https://example.com)")
        assert md.raw_content == "[link](https://example.com)"
    
    def test_strikethrough_preserved(self) -> None:
        """~~text~~ Markdown синтаксис сохраняется."""
        from codelab.client.tui.components.markdown import InlineMarkdown
        
        md = InlineMarkdown("~~strikethrough~~")
        assert md.raw_content == "~~strikethrough~~"
    
    def test_header_preserved(self) -> None:
        """# header Markdown синтаксис сохраняется."""
        from codelab.client.tui.components.markdown import InlineMarkdown
        
        md = InlineMarkdown("# Header")
        assert md.raw_content == "# Header"
    
    def test_empty_text(self) -> None:
        """Пустой текст не вызывает ошибок."""
        from codelab.client.tui.components.markdown import InlineMarkdown
        
        md = InlineMarkdown("")
        assert md.raw_content == ""
    
    def test_raw_content_property(self) -> None:
        """Свойство raw_content возвращает исходный текст."""
        from codelab.client.tui.components.markdown import InlineMarkdown
        
        md = InlineMarkdown("**test**")
        assert md.raw_content == "**test**"
    
    def test_literal_rich_tags_no_crash(self) -> None:
        """Литеральные Rich-теги не вызывают MarkupError."""
        from codelab.client.tui.components.markdown import InlineMarkdown
        
        # Это ключевой тест — раньше [/bold] в тексте LLM ломал Rich парсер
        md = InlineMarkdown("text with [/bold] tag")
        assert md.raw_content == "text with [/bold] tag"


class TestCodeBlock:
    """Тесты для CodeBlock компонента."""
    
    def test_code_property(self) -> None:
        """Свойство code возвращает исходный код."""
        from codelab.client.tui.components.markdown import CodeBlock
        
        code = "def hello():\n    pass"
        block = CodeBlock(code, language="python")
        assert block.code == code
    
    def test_language_property(self) -> None:
        """Свойство language возвращает язык."""
        from codelab.client.tui.components.markdown import CodeBlock
        
        block = CodeBlock("code", language="python")
        assert block.language == "python"
    
    def test_default_language(self) -> None:
        """По умолчанию язык - text."""
        from codelab.client.tui.components.markdown import CodeBlock
        
        block = CodeBlock("code")
        assert block.language == "text"


class TestMessageRole:
    """Тесты для MessageRole enum."""
    
    def test_user_role(self) -> None:
        """Роль USER."""
        from codelab.client.tui.components.message_bubble import MessageRole
        
        assert MessageRole.USER.value == "user"
    
    def test_assistant_role(self) -> None:
        """Роль ASSISTANT."""
        from codelab.client.tui.components.message_bubble import MessageRole
        
        assert MessageRole.ASSISTANT.value == "assistant"
    
    def test_system_role(self) -> None:
        """Роль SYSTEM."""
        from codelab.client.tui.components.message_bubble import MessageRole
        
        assert MessageRole.SYSTEM.value == "system"
    
    def test_error_role(self) -> None:
        """Роль ERROR."""
        from codelab.client.tui.components.message_bubble import MessageRole
        
        assert MessageRole.ERROR.value == "error"


class TestMessageBubble:
    """Тесты для MessageBubble компонента."""
    
    def test_role_property(self) -> None:
        """Свойство role возвращает роль."""
        from codelab.client.tui.components.message_bubble import MessageBubble, MessageRole
        
        bubble = MessageBubble(role=MessageRole.USER, content="test")
        assert bubble.role == MessageRole.USER
    
    def test_content_property(self) -> None:
        """Свойство content возвращает контент."""
        from codelab.client.tui.components.message_bubble import MessageBubble, MessageRole
        
        bubble = MessageBubble(role=MessageRole.USER, content="Hello")
        assert bubble.content == "Hello"
    
    def test_timestamp_property(self) -> None:
        """Свойство timestamp возвращает время."""
        from codelab.client.tui.components.message_bubble import MessageBubble, MessageRole
        
        ts = datetime.now()
        bubble = MessageBubble(role=MessageRole.USER, content="test", timestamp=ts)
        assert bubble.timestamp == ts
    
    def test_from_dict_basic(self) -> None:
        """Создание из словаря с базовыми полями."""
        from codelab.client.tui.components.message_bubble import MessageBubble, MessageRole
        
        msg_dict = {"role": "user", "content": "Hello"}
        bubble = MessageBubble.from_dict(msg_dict)
        assert bubble.role == MessageRole.USER
        assert bubble.content == "Hello"
    
    def test_from_dict_with_type(self) -> None:
        """Создание из словаря с полем type вместо role."""
        from codelab.client.tui.components.message_bubble import MessageBubble, MessageRole
        
        msg_dict = {"type": "assistant", "content": "Hi"}
        bubble = MessageBubble.from_dict(msg_dict)
        assert bubble.role == MessageRole.ASSISTANT
    
    def test_from_dict_with_timestamp(self) -> None:
        """Создание из словаря с timestamp."""
        from codelab.client.tui.components.message_bubble import MessageBubble
        
        ts = datetime.now()
        msg_dict = {"role": "user", "content": "test", "timestamp": ts}
        bubble = MessageBubble.from_dict(msg_dict)
        assert bubble.timestamp == ts
    
    def test_from_dict_invalid_role(self) -> None:
        """При невалидной роли используется USER."""
        from codelab.client.tui.components.message_bubble import MessageBubble, MessageRole
        
        msg_dict = {"role": "invalid", "content": "test"}
        bubble = MessageBubble.from_dict(msg_dict)
        assert bubble.role == MessageRole.USER


class TestTurnStatus:
    """Тесты для TurnStatus enum."""
    
    def test_all_statuses(self) -> None:
        """Все статусы определены."""
        from codelab.client.tui.components.session_turn import TurnStatus
        
        assert TurnStatus.PENDING.value == "pending"
        assert TurnStatus.STREAMING.value == "streaming"
        assert TurnStatus.COMPLETE.value == "complete"
        assert TurnStatus.ERROR.value == "error"
        assert TurnStatus.CANCELLED.value == "cancelled"


class TestTurnData:
    """Тесты для TurnData dataclass."""
    
    def test_basic_creation(self) -> None:
        """Базовое создание TurnData."""
        from codelab.client.tui.components.session_turn import TurnData, TurnStatus
        
        data = TurnData(
            turn_id="turn-1",
            user_content="Hello",
        )
        assert data.turn_id == "turn-1"
        assert data.user_content == "Hello"
        assert data.status == TurnStatus.PENDING
    
    def test_full_creation(self) -> None:
        """Полное создание TurnData со всеми полями."""
        from codelab.client.tui.components.session_turn import TurnData, TurnStatus
        
        ts = datetime.now()
        data = TurnData(
            turn_id="turn-1",
            user_content="Hello",
            user_timestamp=ts,
            assistant_content="Hi",
            assistant_timestamp=ts,
            status=TurnStatus.COMPLETE,
            error_message=None,
            tool_calls=[{"name": "test"}],
        )
        assert data.status == TurnStatus.COMPLETE
        assert data.assistant_content == "Hi"
        assert data.tool_calls == [{"name": "test"}]


class TestSessionTurn:
    """Тесты для SessionTurn компонента."""
    
    def test_user_content_property(self) -> None:
        """Свойство user_content возвращает промпт пользователя."""
        from codelab.client.tui.components.session_turn import SessionTurn
        
        turn = SessionTurn(turn_id="turn-1", user_content="Hello")
        assert turn.user_content == "Hello"
    
    def test_assistant_content_property(self) -> None:
        """Свойство assistant_content возвращает ответ."""
        from codelab.client.tui.components.session_turn import SessionTurn
        
        turn = SessionTurn(
            turn_id="turn-1",
            user_content="Hello",
            assistant_content="Hi",
        )
        assert turn.assistant_content == "Hi"
    
    def test_tool_calls_property(self) -> None:
        """Свойство tool_calls возвращает копию списка."""
        from codelab.client.tui.components.session_turn import SessionTurn
        
        tools = [{"name": "test"}]
        turn = SessionTurn(
            turn_id="turn-1",
            user_content="Hello",
            tool_calls=tools,
        )
        result = turn.tool_calls
        assert result == tools
        assert result is not tools  # Копия, не оригинал
    
    def test_from_data(self) -> None:
        """Создание из TurnData."""
        from codelab.client.tui.components.session_turn import SessionTurn, TurnData, TurnStatus
        
        data = TurnData(
            turn_id="turn-1",
            user_content="Hello",
            assistant_content="Hi",
            status=TurnStatus.COMPLETE,
        )
        turn = SessionTurn.from_data(data)
        assert turn.turn_id == "turn-1"
        assert turn.user_content == "Hello"
        assert turn.assistant_content == "Hi"


class TestDateSeparator:
    """Тесты для DateSeparator компонента."""
    
    def test_today_label(self) -> None:
        """Сегодняшняя дата показывается как 'Сегодня'."""
        from codelab.client.tui.components.message_list import DateSeparator
        
        today = datetime.now()
        sep = DateSeparator(today)
        # Проверяем, что виджет создается без ошибок
        assert sep is not None
    
    def test_past_date(self) -> None:
        """Прошлая дата показывается в формате дата."""
        from datetime import timedelta
        
        from codelab.client.tui.components.message_list import DateSeparator
        
        past = datetime.now() - timedelta(days=10)
        sep = DateSeparator(past)
        assert sep is not None


class TestMessageList:
    """Тесты для MessageList компонента."""
    
    def test_messages_property(self) -> None:
        """Свойство messages возвращает копию списка."""
        from codelab.client.tui.components.message_list import MessageList
        
        messages = [{"role": "user", "content": "test"}]
        msg_list = MessageList(messages=messages)
        result = msg_list.messages
        assert result == messages
        assert result is not messages  # Копия
    
    def test_message_count(self) -> None:
        """Свойство message_count возвращает количество."""
        from codelab.client.tui.components.message_list import MessageList
        
        messages = [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
        ]
        msg_list = MessageList(messages=messages)
        assert msg_list.message_count == 2
    
    def test_empty_message_count(self) -> None:
        """Пустой список имеет count = 0."""
        from codelab.client.tui.components.message_list import MessageList
        
        msg_list = MessageList()
        assert msg_list.message_count == 0
    
    def test_is_streaming_default(self) -> None:
        """По умолчанию streaming не активен."""
        from codelab.client.tui.components.message_list import MessageList
        
        msg_list = MessageList()
        assert msg_list.is_streaming is False
    
    def test_is_thinking_default(self) -> None:
        """По умолчанию thinking не показан."""
        from codelab.client.tui.components.message_list import MessageList
        
        msg_list = MessageList()
        assert msg_list.is_thinking is False


class TestStreamingText:
    """Тесты для StreamingText компонента."""
    
    def test_text_reactive(self) -> None:
        """Реактивное свойство text."""
        from codelab.client.tui.components.streaming_text import StreamingText
        
        st = StreamingText("initial")
        assert st.text == "initial"
        st.text = "updated"
        assert st.text == "updated"
    
    def test_set_text(self) -> None:
        """Метод set_text обновляет текст."""
        from codelab.client.tui.components.streaming_text import StreamingText
        
        st = StreamingText()
        st.set_text("new text")
        assert st.text == "new text"
    
    def test_clear(self) -> None:
        """Метод clear очищает текст."""
        from codelab.client.tui.components.streaming_text import StreamingText
        
        st = StreamingText("content")
        st.clear()
        assert st.text == ""


class TestThinkingIndicator:
    """Тесты для ThinkingIndicator компонента."""
    
    def test_creation(self) -> None:
        """Создание индикатора."""
        from codelab.client.tui.components.streaming_text import ThinkingIndicator
        
        indicator = ThinkingIndicator("Testing")
        assert indicator._label == "Testing"
    
    def test_default_label(self) -> None:
        """Метка по умолчанию - 'Thinking'."""
        from codelab.client.tui.components.streaming_text import ThinkingIndicator
        
        indicator = ThinkingIndicator()
        assert indicator._label == "Thinking"
    
    def test_set_label(self) -> None:
        """Метод set_label обновляет метку."""
        from codelab.client.tui.components.streaming_text import ThinkingIndicator
        
        indicator = ThinkingIndicator()
        indicator.set_label("Processing")
        assert indicator._label == "Processing"


class TestComponentsExport:
    """Тесты экспорта компонентов из __init__.py."""
    
    def test_markdown_exports(self) -> None:
        """Markdown компоненты экспортируются."""
        from codelab.client.tui.components import CodeBlock, InlineMarkdown, MarkdownViewer
        
        assert MarkdownViewer is not None
        assert InlineMarkdown is not None
        assert CodeBlock is not None
    
    def test_streaming_exports(self) -> None:
        """Streaming компоненты экспортируются."""
        from codelab.client.tui.components import (
            StreamingText,
            ThinkingIndicator,
            TypewriterText,
        )
        
        assert StreamingText is not None
        assert TypewriterText is not None
        assert ThinkingIndicator is not None
    
    def test_message_exports(self) -> None:
        """Message компоненты экспортируются."""
        from codelab.client.tui.components import (
            Avatar,
            DateSeparator,
            MessageBubble,
            MessageList,
            MessageRole,
        )
        
        assert Avatar is not None
        assert MessageBubble is not None
        assert MessageRole is not None
        assert MessageList is not None
        assert DateSeparator is not None
    
    def test_session_turn_exports(self) -> None:
        """SessionTurn компоненты экспортируются."""
        from codelab.client.tui.components import SessionTurn, TurnData, TurnStatus
        
        assert SessionTurn is not None
        assert TurnStatus is not None
        assert TurnData is not None
