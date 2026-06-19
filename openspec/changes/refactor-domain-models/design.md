# Design: Рефакторизация доменных моделей

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
│   ├── state.py               # РЕФАКТОРИНГ: тонкие DTO
│   └── dto/                   # НОВЫЙ: Transport DTO
│       ├── session_dto.py
│       ├── tool_call_dto.py
│       └── history_dto.py
└── mapping/                   # НОВЫЙ: Mapping Layer
    ├── session_mapper.py
    ├── tool_call_mapper.py
    └── history_mapper.py
```

**Обоснование:**
- SRP: каждый слой отвечает за свою абстракцию
- DIP: domain не зависит от transport
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

# Transport Layer (server/protocol/dto/tool_call_dto.py)
class ToolCallDTO(BaseModel):
    """DTO для ACP wire format."""
    toolCallId: str
    title: str
    kind: ToolKind
    status: ToolCallStatus
    content: list[dict[str, Any]] | None = None
    locations: list[ToolCallLocationDTO] | None = None
    rawInput: dict[str, Any] | None = None
    rawOutput: dict[str, Any] | None = None

# Mapping Layer (server/mapping/tool_call_mapper.py)
class ToolCallMapper:
    @staticmethod
    def to_dto(domain: ToolCall) -> ToolCallDTO:
        return ToolCallDTO(
            toolCallId=domain.id,
            title=domain.tool_name,
            kind=ToolKind.from_tool_name(domain.tool_name),
            status=domain.status.to_acp_status(),
            rawInput=domain.arguments,
            rawOutput=domain.result.to_dict() if domain.result else None,
        )
    
    @staticmethod
    def to_domain(dto: ToolCallDTO) -> ToolCall:
        return ToolCall(
            id=dto.toolCallId,
            tool_name=dto.title,
            arguments=dto.rawInput or {},
            status=ToolCallStatus.from_acp_status(dto.status),
        )
```

**Обоснование:**
- Устраняет дублирование
- Domain модель стабильна, DTO может меняться с ACP spec
- Маппинг явный и тестируемый

**Миграция:**
1. Создать domain `ToolCall` и `ToolCallDTO`
2. Заменить `ToolCallState` на `ToolCallDTO` в `SessionState`
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

# Transport Layer (server/protocol/dto/history_dto.py)
class HistoryMessageDTO(BaseModel):
    """DTO для ACP wire format."""
    role: str
    content: list[ContentBlockDTO] | str
    timestamp: str | None = None
    tool_calls: list[ToolCallDTO] | None = None
    tool_call_id: str | None = None

# Mapping Layer
class HistoryMapper:
    @staticmethod
    def to_dto(domain: ConversationMessage) -> HistoryMessageDTO:
        return HistoryMessageDTO(
            role=domain.role.value,
            content=ContentBlockMapper.to_dto_list(domain.content),
            timestamp=domain.timestamp.isoformat(),
            tool_calls=[ToolCallMapper.to_dto(tc) for tc in domain.tool_calls],
            tool_call_id=domain.tool_call_id,
        )
    
    @staticmethod
    def to_domain(dto: HistoryMessageDTO) -> ConversationMessage:
        return ConversationMessage(
            role=MessageRole(dto.role),
            content=ContentBlockMapper.to_domain(dto.content),
            timestamp=datetime.fromisoformat(dto.timestamp) if dto.timestamp else datetime.now(),
            tool_calls=[ToolCallMapper.to_domain(tc) for tc in (dto.tool_calls or [])],
            tool_call_id=dto.tool_call_id,
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

# Transport Layer (server/protocol/dto/session_dto.py)
class SessionStateDTO(BaseModel):
    """Тонкий DTO для сериализации."""
    session_id: str
    config: SessionConfigDTO
    history: list[HistoryMessageDTO]
    tool_calls: dict[str, ToolCallDTO]
    permissions: PermissionStateDTO
    plan: AgentPlanDTO
    multi_agent: MultiAgentStateDTO
    schema_version: int = 4

# Mapping Layer
class SessionMapper:
    @staticmethod
    def to_dto(domain: Session) -> SessionStateDTO: ...
    
    @staticmethod
    def to_domain(dto: SessionStateDTO) -> Session: ...
```

**Обоснование:**
- SRP: каждый агрегат отвечает за свою область
- Инкапсуляция: бизнес-логика в агрегатах
- Тестируемость: каждый агрегат тестируется отдельно
- Эволюционируемость: можно менять DTO независимо от domain

**Миграция:**
1. Создать domain агрегаты
2. Создать DTO
3. Создать мапперы
4. Заменить `SessionState` на `SessionStateDTO` в storage
5. Обновить handlers для работы с domain `Session`
6. Миграция storage format (schema_version: 4)

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
class SessionStateDTO(BaseModel):
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
