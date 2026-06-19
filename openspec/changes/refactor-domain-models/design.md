# Design: Рефакторизация доменных моделей

## Именование слоёв

В проекте используются три уровня моделей:

| Слой | Название | Пример | Назначение |
|------|----------|--------|------------|
| **Domain** | Domain Model | `ToolCall`, `Session` | Бизнес-сущности с логикой (frozen dataclass) |
| **Protocol** | ACP Protocol Model | `ToolCallState`, `SessionState` | Контракты ACP протокола (Pydantic) |
| **Mapping** | Mapper | `ToolCallMapper`, `SessionMapper` | Конвертеры между слоями |

**Важно:** Protocol модели — это НЕ DTO. Это контракты ACP протокола, которые:
- Определяют wire format для `session/update`, `session/new`, etc.
- Содержат валидацию через Pydantic
- Поддерживают сериализацию/десиализацию
- Соответствуют ACP спецификации (08-Tool Calls, 03-Session Setup, etc.)

### Таблица соответствия

| Domain Model | ACP Protocol Model | Маппер | ACP Spec |
|--------------|-------------------|--------|----------|
| `ToolCall` | `ToolCallState` | `ToolCallMapper` | 08-Tool Calls |
| `ConversationMessage` | `HistoryMessage` | `HistoryMapper` | 05-Prompt Turn |
| `PlanEntry` | `PlanStep` | `PlanMapper` | 11-Agent Plan |
| `UserPrompt` | `ContentBlock` | `PromptMapper` | 06-Content |
| `Session` | `SessionState` | `SessionMapper` | 03-Session Setup |

## Архитектурные решения

### Решение 1: Domain Layer в server

**Проблема:** В server отсутствует Domain Layer. Все модели находятся в protocol/state.py и смешивают уровни.

**Решение:** Создать `server/domain/` с бизнес-сущностями.

```
server/
├── domain/                    # НОВЫЙ: Domain Layer
│   ├── __init__.py
│   ├── session.py             # Session aggregate
│   ├── tool_call.py           # ToolCall entity
│   ├── conversation.py        # ConversationMessage, MessageContent
│   ├── prompt.py              # UserPrompt
│   ├── plan.py                # PlanEntry
│   └── value_objects.py       # SessionId, FileLocation, etc.
├── protocol/
│   ├── state.py               # РЕФАКТОРИНГ: ACP Protocol Models (SessionState, ToolCallState)
│   ├── content/               # ContentValidator, ContentExtractor
│   └── handlers/              # ToolCallHandler, PromptOrchestrator
└── mapping/                   # НОВЫЙ: Mapping Layer
    ├── session_mapper.py
    ├── tool_call_mapper.py
    └── history_mapper.py
```

**Обоснование:**
- SRP: каждый слой отвечает за свою абстракцию
- DIP: domain не зависит от protocol
- Testability: domain модели тестируются изолированно

**Альтернативы:**
1. Оставить как есть — отклонено, архитектурный долг растёт
2. Использовать существующий `server/models.py` — отклонено, там мёртвый код

### Решение 2: Разделение ToolCall

**Проблема:** Три модели `ToolCall` в разных местах.

**Решение:**

```python
# Domain Layer (server/domain/tool_call.py)
@dataclass(frozen=True)
class ToolCall:
    """Domain entity — внутреннее представление tool call."""
    id: str
    tool_name: str
    arguments: dict[str, Any]
    status: ToolCallStatus  # domain enum: pending, running, completed, failed
    result: ToolResult | None = None
    
    @property
    def is_terminal(self) -> bool:
        return self.status in (ToolCallStatus.COMPLETED, ToolCallStatus.FAILED)

# ACP Protocol Model (server/protocol/state.py)
class ToolCallState(BaseModel):
    """ACP Protocol Model — контракт tool call согласно ACP 08-Tool Calls.
    
    Wire format для session/update notification с sessionUpdate="tool_call"
    и sessionUpdate="tool_call_update".
    
    НЕ является domain моделью. Для бизнес-логики использовать domain ToolCall.
    Конвертация через ToolCallMapper.
    """
    toolCallId: str
    title: str
    kind: ToolKind
    status: ToolCallStatus
    content: list[dict[str, Any]] | None = None
    locations: list[ToolCallLocation] | None = None
    rawInput: dict[str, Any] | None = None
    rawOutput: dict[str, Any] | None = None

# Mapping Layer (server/mapping/tool_call_mapper.py)
class ToolCallMapper:
    @staticmethod
    def to_protocol(domain: ToolCall) -> ToolCallState:
        return ToolCallState(
            toolCallId=domain.id,
            title=domain.tool_name,
            kind=ToolKind.from_tool_name(domain.tool_name),
            status=domain.status.to_acp_status(),
            rawInput=domain.arguments,
            rawOutput=domain.result.to_dict() if domain.result else None,
        )
    
    @staticmethod
    def to_domain(protocol: ToolCallState) -> ToolCall:
        return ToolCall(
            id=protocol.toolCallId,
            tool_name=protocol.title,
            arguments=protocol.rawInput or {},
            status=ToolCallStatus.from_acp_status(protocol.status),
        )
```

**Обоснование:**
- Устраняет дублирование
- Domain модель стабильна, Protocol модель может меняться с ACP spec
- Маппинг явный и тестируемый

**Миграция:**
1. Создать domain `ToolCall`
2. Обновить `ToolCallState` (ACP Protocol Model) с новыми полями
3. Обновить handlers для использования маппера
4. Удалить мёртвый `ToolCall` из `models.py`

### Решение 3: Разделение HistoryMessage

**Проблема:** `HistoryMessage.content` — union из 3 типов.

**Решение:**

```python
# Domain Layer (server/domain/conversation.py)
@dataclass(frozen=True)
class MessageContent:
    """Domain model для содержимого сообщения."""
    text: str
    resources: list[Resource] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)

@dataclass(frozen=True)
class ConversationMessage:
    """Domain entity — сообщение в истории."""
    role: MessageRole  # enum: USER, ASSISTANT, SYSTEM, TOOL
    content: MessageContent
    timestamp: datetime
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # для role=TOOL

# ACP Protocol Model (server/protocol/state.py)
class HistoryMessage(BaseModel):
    """ACP Protocol Model — контракт сообщения истории согласно ACP 05-Prompt Turn.
    
    Wire format для хранения истории сообщений в SessionState.
    
    НЕ является domain моделью. Для бизнес-логики использовать domain ConversationMessage.
    Конвертация через HistoryMapper.
    """
    role: str
    content: list[ContentBlock] | str
    timestamp: str | None = None
    tool_calls: list[ToolCallState] | None = None
    tool_call_id: str | None = None

# Mapping Layer
class HistoryMapper:
    @staticmethod
    def to_protocol(domain: ConversationMessage) -> HistoryMessage:
        return HistoryMessage(
            role=domain.role.value,
            content=ContentBlockMapper.to_protocol_list(domain.content),
            timestamp=domain.timestamp.isoformat(),
            tool_calls=[ToolCallMapper.to_protocol(tc) for tc in domain.tool_calls],
            tool_call_id=domain.tool_call_id,
        )
    
    @staticmethod
    def to_domain(protocol: HistoryMessage) -> ConversationMessage:
        return ConversationMessage(
            role=MessageRole(protocol.role),
            content=ContentBlockMapper.to_domain(protocol.content),
            timestamp=datetime.fromisoformat(protocol.timestamp) if protocol.timestamp else datetime.now(),
            tool_calls=[ToolCallMapper.to_domain(tc) for tc in (protocol.tool_calls or [])],
            tool_call_id=protocol.tool_call_id,
        )
```

**Обоснование:**
- Типизация вместо union
- Domain модель не зависит от JSON structure
- Маппинг обрабатывает все варианты content

### Решение 4: Разбиение SessionState на агрегаты

**Проблема:** God Object с 30+ полями.

**Решение:**

```python
# Domain Layer (server/domain/session.py)
class Session:
    """Aggregate root — сессия."""
    id: SessionId
    config: SessionConfig
    history: ConversationHistory
    tool_calls: ToolCallRegistry
    permissions: PermissionState
    plan: AgentPlan
    multi_agent: MultiAgentState
    
    # Business logic
    def add_message(self, message: ConversationMessage) -> None: ...
    def create_tool_call(self, tool_name: str, arguments: dict) -> ToolCall: ...
    def update_tool_call(self, tool_call_id: str, result: ToolResult) -> None: ...
    def set_permission_policy(self, kind: str, policy: str) -> None: ...

# Value Objects
@dataclass(frozen=True)
class SessionConfig:
    cwd: str
    config_values: dict[str, str]
    active_strategy: str
    runtime_capabilities: ClientCapabilities

@dataclass
class ConversationHistory:
    messages: list[ConversationMessage]
    events: list[DomainEvent]
    
    def add(self, message: ConversationMessage) -> None: ...
    def get_recent(self, n: int) -> list[ConversationMessage]: ...

@dataclass
class ToolCallRegistry:
    calls: dict[str, ToolCall]
    counter: int
    
    def create(self, tool_name: str, arguments: dict) -> ToolCall: ...
    def get(self, tool_call_id: str) -> ToolCall | None: ...
    def update(self, tool_call_id: str, result: ToolResult) -> None: ...

@dataclass
class PermissionState:
    policy: dict[str, str]
    cancelled_requests: set[JsonRpcId]
    
    def is_allowed(self, kind: str) -> bool: ...
    def cancel_request(self, request_id: JsonRpcId) -> None: ...

@dataclass
class AgentPlan:
    steps: list[PlanEntry]
    
    def add_step(self, step: PlanEntry) -> None: ...
    def update_step(self, index: int, status: PlanStatus) -> None: ...

@dataclass
class MultiAgentState:
    active_strategy: str
    active_agents: list[str]
    parent_session_id: str | None
    child_session_ids: list[str]
    is_child_session: bool

# ACP Protocol Model (server/protocol/state.py)
class SessionState(BaseModel):
    """ACP Protocol Model — контракт сессии согласно ACP 03-Session Setup.
    
    Wire format для хранения состояния сессии в storage.
    
    НЕ является domain моделью. Для бизнес-логики использовать domain Session.
    Конвертация через SessionMapper.
    """
    session_id: str
    config: SessionConfig
    history: list[HistoryMessage]
    tool_calls: dict[str, ToolCallState]
    permissions: PermissionState
    plan: AgentPlan
    multi_agent: MultiAgentState
    schema_version: int = 4

# Mapping Layer
class SessionMapper:
    @staticmethod
    def to_protocol(domain: Session) -> SessionState: ...
    
    @staticmethod
    def to_domain(protocol: SessionState) -> Session: ...
```

**Обоснование:**
- SRP: каждый агрегат отвечает за свою область
- Инкапсуляция: бизнес-логика в агрегатах
- Тестируемость: каждый агрегат тестируется отдельно
- Эволюционируемость: можно менять Protocol модели независимо от domain

**Миграция:**
1. Создать domain агрегаты
2. Обновить `SessionState` (ACP Protocol Model) с новой структурой
3. Создать мапперы
4. Обновить handlers для работы с domain `Session`
5. Миграция storage format (schema_version: 4)

### Решение 5: Domain AgentContext

**Проблема:** `AgentContext.prompt` — ACP format.

**Решение:**

```python
# Domain Layer (server/domain/prompt.py)
@dataclass(frozen=True)
class UserPrompt:
    """Domain model для промпта пользователя."""
    text: str
    resources: list[Resource] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    
    @property
    def has_multimodal(self) -> bool:
        return bool(self.resources or self.images)

# Domain AgentContext
@dataclass
class AgentContext:
    session_id: str
    prompt: UserPrompt  # domain model
    conversation_history: list[ConversationMessage]
    available_tools: list[ToolDefinition]
    config: dict[str, str]

# Mapping Layer
class PromptMapper:
    @staticmethod
    def from_acp_blocks(blocks: list[dict]) -> UserPrompt:
        text_parts = []
        resources = []
        images = []
        
        for block in blocks:
            match block.get("type"):
                case "text":
                    text_parts.append(block["text"])
                case "resource":
                    resources.append(Resource.from_acp(block))
                case "image":
                    images.append(Image.from_acp(block))
        
        return UserPrompt(
            text="\n".join(text_parts),
            resources=resources,
            images=images,
        )
    
    @staticmethod
    def to_acp_blocks(prompt: UserPrompt) -> list[dict]:
        blocks = []
        if prompt.text:
            blocks.append({"type": "text", "text": prompt.text})
        for resource in prompt.resources:
            blocks.append(resource.to_acp())
        for image in prompt.images:
            blocks.append(image.to_acp())
        return blocks
```

### Решение 6: Domain ToolExecutionResult

**Проблема:** `content` — ACP format в domain.

**Решение:**

```python
# Domain Layer (server/domain/tool_call.py)
@dataclass(frozen=True)
class FileLocation:
    """Domain model для file location."""
    path: str
    line: int | None = None

@dataclass(frozen=True)
class ToolResult:
    """Domain model для результата tool call."""
    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    locations: list[FileLocation] = field(default_factory=list)

@dataclass
class ToolExecutionResult:
    """Domain model для результата выполнения tool."""
    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    locations: list[FileLocation] = field(default_factory=list)
    
    # НЕ содержит ACP content

# Mapping Layer
class ToolResultMapper:
    @staticmethod
    def to_acp_content(result: ToolExecutionResult) -> list[dict]:
        """Конвертировать domain result в ACP content blocks."""
        blocks = []
        if result.output:
            blocks.append({"type": "text", "text": result.output})
        if result.metadata.get("diff"):
            blocks.append({
                "type": "diff",
                "path": result.metadata["path"],
                "diff": result.metadata["diff"],
            })
        return blocks
```

### Решение 7: Domain PlanEntry

**Проблема:** `PlanStep` не соответствует ACP spec.

**Решение:**

```python
# Domain Layer (server/domain/plan.py)
@dataclass(frozen=True)
class PlanEntry:
    """Domain model для шага плана."""
    content: str
    priority: PlanPriority  # enum: HIGH, MEDIUM, LOW
    status: PlanStatus  # enum: PENDING, IN_PROGRESS, COMPLETED

# Mapping Layer
class PlanMapper:
    @staticmethod
    def to_acp(entries: list[PlanEntry]) -> list[dict]:
        return [
            {
                "content": entry.content,
                "priority": entry.priority.value,
                "status": entry.status.value,
            }
            for entry in entries
        ]
    
    @staticmethod
    def from_acp(blocks: list[dict]) -> list[PlanEntry]:
        return [
            PlanEntry(
                content=block["content"],
                priority=PlanPriority(block["priority"]),
                status=PlanStatus(block["status"]),
            )
            for block in blocks
        ]
```

### Решение 8: Типизированные ClientCapabilities

**Проблема:** `dict[str, Any]` вместо типизированной модели.

**Решение:**

```python
# Domain Layer (client/domain/entities.py)
@dataclass(frozen=True)
class ClientCapabilities:
    """Domain model для возможностей клиента."""
    fs_read: bool = False
    fs_write: bool = False
    terminal: bool = False
    image_prompts: bool = False
    embedded_context: bool = False
    
    @property
    def supports_fs(self) -> bool:
        return self.fs_read or self.fs_write
    
    def can_read_files(self) -> bool:
        return self.fs_read
    
    def can_write_files(self) -> bool:
        return self.fs_write

@dataclass
class Session:
    id: SessionId
    config: SessionConfig
    capabilities: ClientCapabilities  # типизированная модель
    status: SessionStatus
    
    def is_authenticated(self) -> bool: ...
    def supports_fs(self) -> bool:
        return self.capabilities.supports_fs
```

### Решение 9: Tool Execution Result с raw_output и locations

**Проблема:** `ToolExecutionResult` не содержит полей для ACP `rawOutput` и `locations`.

**Решение:**

```python
# Domain Layer (server/tools/base.py)
@dataclass
class ToolExecutionResult:
    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    content: list[dict[str, Any]] = field(default_factory=list)
    locations: list[FileLocation] = field(default_factory=list)  # NEW
    raw_output: dict[str, Any] = field(default_factory=dict)     # NEW
```

**raw_output для каждого типа tool:**

| Tool | `raw_output` |
|------|--------------|
| `fs/read_text_file` | `{"content": "...", "bytes_read": 1024}` |
| `fs/write_text_file` | `{"bytes_written": 512, "diff": "..."}` |
| `terminal/create` | `{"terminal_id": "term_xyz"}` |
| `terminal/wait_for_exit` | `{"exit_code": 0, "signal": null, "output": "..."}` |
| `MCP tools` | `{"result": {...}}` |

**locations для каждого типа tool:**

| Tool | `locations` |
|------|-------------|
| `fs/read_text_file` | `[FileLocation(path, line)]` |
| `fs/write_text_file` | `[FileLocation(path)]` |
| `terminal/*` | `[]` (нет file locations) |
| `MCP tools` | `[]` (внешние ресурсы, не файлы IDE) |

**Обоснование:**
- `raw_output` — ACP-специфичный вывод для клиента (согласно ACP 08-Tool Calls)
- `metadata` — внутренние данные для отладки (не для клиента)
- MCP tools не возвращают `locations` — работают с внешними ресурсами

### Решение 10: Follow-Along сервис

**Проблема:** Клиент не имеет механизма для автоматического открытия файлов при tool calls.

**Решение:**

```python
# Client Layer (client/infrastructure/services/follow_along.py)
class FileOpener(Protocol):
    async def open(self, path: str, line: int | None = None) -> None: ...

class FollowAlongService:
    def __init__(self, file_opener: FileOpener, enabled: bool = True):
        self._file_opener = file_opener
        self._enabled = enabled
    
    async def on_tool_call_updated(self, tool_call: dict[str, Any]) -> None:
        if not self._enabled:
            return
        locations = tool_call.get("locations", [])
        if not locations:
            return
        first = locations[0]
        await self._file_opener.open(
            path=first["path"],
            line=first.get("line"),
        )
```

**Интеграция в ToolCallHandler:**
```python
class ToolCallHandler:
    def __init__(self, follow_along: FollowAlongService | None = None):
        self._follow_along = follow_along
    
    def _handle_tool_call_updated(self, update, context):
        # ... обновление состояния ...
        if self._follow_along and locations:
            await self._follow_along.on_tool_call_updated(tool_call)
```

**Feature flag НЕ нужен:**
- Follow-along — стандартная функция IDE
- Если tool call не имеет `locations` — follow-along не срабатывает
- Нет риска поломки существующего функционала

**Обоснование:**
- Observer Pattern — реагирует на обновления tool calls
- DIP — зависит от `FileOpener` Protocol, не от конкретной реализации
- Testability — `StubFileOpener` для тестов

## Зависимости между решениями

```
Решение 4 (SessionState) зависит от:
  → Решение 2 (ToolCall)
  → Решение 3 (HistoryMessage)
  → Решение 7 (PlanEntry)

Решение 5 (AgentContext) зависит от:
  → Решение 6 (ToolExecutionResult)

Решение 8 (ClientCapabilities) — независимо
```

## Миграция storage format

**Текущая версия:** schema_version = 3
**Новая версия:** schema_version = 4

```python
class SessionState(BaseModel):
    """ACP Protocol Model — контракт сессии согласно ACP 03-Session Setup."""
    
    @model_validator(mode="before")
    @classmethod
    def migrate_schema(cls, data: dict) -> dict:
        version = data.get("schema_version", 0)
        
        if version < 4:
            # Миграция: плоские поля → агрегаты
            data["config"] = {
                "cwd": data.pop("cwd", ""),
                "config_values": data.pop("config_values", {}),
                "active_strategy": data.pop("active_strategy", "single"),
            }
            data["tool_calls"] = {
                "calls": data.pop("tool_calls", {}),
                "counter": data.pop("tool_call_counter", 0),
            }
            # ... другие миграции
            data["schema_version"] = 4
        
        return data
```

## Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Поломать storage | Высокая | Высокое | Миграция в model_validator, тесты |
| Поломать handlers | Средняя | Высокое | Поэтапная миграция, тесты |
| Длительная миграция | Средняя | Среднее | Независимые фазы |
| Неполная миграция | Средняя | Среднее | TODO-комментарии |

## План внедрения

См. `tasks.md` для детального поэтапного плана.
