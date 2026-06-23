# LSP Integration — Интеграция с Language Server Protocol

> Компоненты для интеграции с LSP: определение символов, ссылки, переименование

## Оглавление

- [Обзор](#обзор)
- [LSPClient](#lspclient)
- [DefinitionResolver](#definitionresolver)
- [ReferenceResolver](#referenceresolver)
- [RenameEngine](#renameengine)
- [Интеграция с ContextManager](#интеграция-с-contextmanager)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

LSP Integration отвечает за **интеграцию с Language Server Protocol**: точное определение символов, поиск ссылок, переименование.

**Компоненты:**
- `LSPClient` — клиент LSP протокола
- `DefinitionResolver` — резолвинг определений символов
- `ReferenceResolver` — резолвинг ссылок на символы
- `RenameEngine` — движок переименования

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ContextManager                                              │
│  └─ LSPClient           ← LSP Integration                    │
│  └─ DefinitionResolver  ← LSP Integration                    │
│  └─ ReferenceResolver   ← LSP Integration                    │
│  └─ RenameEngine        ← LSP Integration                    │
└─────────────────────────────────────────────────────────────┘
```

---

## LSPClient

### Назначение

Клиент LSP протокола: взаимодействие с language server.

### Интерфейс

```python
@dataclass
class Location:
    """Местоположение в файле."""
    file_path: str
    line: int
    character: int

@dataclass
class SymbolInformation:
    """Информация о символе."""
    name: str
    kind: int  # LSP SymbolKind
    location: Location
    container_name: str | None

class LSPClient:
    """Клиент LSP протокола."""
    
    def __init__(self, cwd: str):
        self.cwd = cwd
        self.server_process: asyncio.subprocess.Process | None = None
        self.request_id = 0
    
    async def start_server(self, language: str) -> None:
        """Запустить language server."""
        commands = {
            "typescript": "typescript-language-server --stdio",
            "python": "pylsp",
            "go": "gopls",
        }
        
        command = commands.get(language)
        if not command:
            raise ValueError(f"Unsupported language: {language}")
        
        self.server_process = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd
        )
        
        # Инициализация
        await self._initialize()
    
    async def _initialize(self) -> None:
        """Инициализировать LSP server."""
        await self._send_request("initialize", {
            "processId": os.getpid(),
            "rootUri": f"file://{self.cwd}",
            "capabilities": {}
        })
        
        await self._send_notification("initialized", {})
    
    async def get_definition(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> list[Location]:
        """Получить определение символа."""
        result = await self._send_request("textDocument/definition", {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character}
        })
        
        return self._parse_locations(result)
    
    async def get_references(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> list[Location]:
        """Получить ссылки на символ."""
        result = await self._send_request("textDocument/references", {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True}
        })
        
        return self._parse_locations(result)
    
    async def get_symbols(self, file_path: str) -> list[SymbolInformation]:
        """Получить символы в файле."""
        result = await self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": f"file://{file_path}"}
        })
        
        return self._parse_symbols(result)
    
    async def rename_symbol(
        self,
        file_path: str,
        line: int,
        character: int,
        new_name: str,
    ) -> dict[str, list[dict]]:
        """Переименовать символ."""
        result = await self._send_request("textDocument/rename", {
            "textDocument": {"uri": f"file://{file_path}"},
            "position": {"line": line, "character": character},
            "newName": new_name
        })
        
        return self._parse_workspace_edit(result)
    
    async def _send_request(self, method: str, params: dict) -> dict:
        """Отправить LSP request."""
        self.request_id += 1
        
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }
        
        await self._send_message(request)
        
        # Ждать ответ
        response = await self._receive_message()
        return response.get("result", {})
    
    async def _send_notification(self, method: str, params: dict) -> None:
        """Отправить LSP notification."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        await self._send_message(notification)
    
    async def _send_message(self, message: dict) -> None:
        """Отправить сообщение."""
        content = json.dumps(message)
        header = f"Content-Length: {len(content)}\r\n\r\n"
        
        self.server_process.stdin.write(header.encode() + content.encode())
        await self.server_process.stdin.drain()
    
    async def _receive_message(self) -> dict:
        """Получить сообщение."""
        # Читать header
        header = await self.server_process.stdout.readline()
        content_length = int(header.decode().split(":")[1].strip())
        
        # Читать пустую строку
        await self.server_process.stdout.readline()
        
        # Читать content
        content = await self.server_process.stdout.readexactly(content_length)
        
        return json.loads(content.decode())
    
    def _parse_locations(self, result: Any) -> list[Location]:
        """Парсить locations из LSP response."""
        if not result:
            return []
        
        if isinstance(result, dict):
            result = [result]
        
        locations = []
        for item in result:
            uri = item["uri"].replace("file://", "")
            line = item["range"]["start"]["line"]
            character = item["range"]["start"]["character"]
            
            locations.append(Location(
                file_path=uri,
                line=line,
                character=character
            ))
        
        return locations
    
    def _parse_symbols(self, result: Any) -> list[SymbolInformation]:
        """Парсить symbols из LSP response."""
        if not result:
            return []
        
        symbols = []
        for item in result:
            symbols.append(SymbolInformation(
                name=item["name"],
                kind=item["kind"],
                location=Location(
                    file_path=item["location"]["uri"].replace("file://", ""),
                    line=item["location"]["range"]["start"]["line"],
                    character=item["location"]["range"]["start"]["character"]
                ),
                container_name=item.get("containerName")
            ))
        
        return symbols
    
    def _parse_workspace_edit(self, result: Any) -> dict[str, list[dict]]:
        """Парсить workspace edit из LSP response."""
        if not result:
            return {}
        
        changes = {}
        for uri, edits in result.get("changes", {}).items():
            file_path = uri.replace("file://", "")
            changes[file_path] = edits
        
        return changes
    
    async def shutdown(self) -> None:
        """Завершить работу language server."""
        if self.server_process:
            await self._send_request("shutdown", {})
            await self._send_notification("exit", {})
            self.server_process.terminate()
            await self.server_process.wait()
```

---

## DefinitionResolver

### Назначение

Резолвинг определений символов: переход к определению.

### Интерфейс

```python
class DefinitionResolver:
    """Резолвинг определений символов."""
    
    def __init__(self, lsp_client: LSPClient):
        self.lsp_client = lsp_client
    
    async def resolve(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> list[Location]:
        """
        Резолвить определение символа.
        
        Args:
            file_path: Путь к файлу
            line: Строка (0-based)
            character: Символ (0-based)
        
        Returns:
            Список местоположений определений
        """
        return await self.lsp_client.get_definition(file_path, line, character)
    
    async def resolve_symbol(
        self,
        symbol_name: str,
        file_path: str,
    ) -> list[Location]:
        """
        Резолвить определение по имени символа.
        
        Сначала найти символ в файле, потом резолвить.
        """
        # Найти символ в файле
        symbols = await self.lsp_client.get_symbols(file_path)
        
        for symbol in symbols:
            if symbol.name == symbol_name:
                return await self.resolve(
                    file_path,
                    symbol.location.line,
                    symbol.location.character
                )
        
        return []
```

---

## ReferenceResolver

### Назначение

Резолвинг ссылок на символы: найти все использования символа.

### Интерфейс

```python
class ReferenceResolver:
    """Резолвинг ссылок на символы."""
    
    def __init__(self, lsp_client: LSPClient):
        self.lsp_client = lsp_client
    
    async def resolve(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> list[Location]:
        """
        Резолвить ссылки на символ.
        
        Args:
            file_path: Путь к файлу
            line: Строка (0-based)
            character: Символ (0-based)
        
        Returns:
            Список местоположений ссылок
        """
        return await self.lsp_client.get_references(file_path, line, character)
    
    async def find_all_uses(
        self,
        symbol_name: str,
        file_path: str,
    ) -> list[Location]:
        """
        Найти все использования символа.
        
        Сначала найти символ в файле, потом найти все ссылки.
        """
        # Найти символ в файле
        symbols = await self.lsp_client.get_symbols(file_path)
        
        for symbol in symbols:
            if symbol.name == symbol_name:
                return await self.resolve(
                    file_path,
                    symbol.location.line,
                    symbol.location.character
                )
        
        return []
```

---

## RenameEngine

### Назначение

Движок переименования: безопасное переименование символов во всём проекте.

### Интерфейс

```python
class RenameEngine:
    """Движок переименования."""
    
    def __init__(self, lsp_client: LSPClient):
        self.lsp_client = lsp_client
    
    async def rename(
        self,
        file_path: str,
        line: int,
        character: int,
        new_name: str,
    ) -> dict[str, list[dict]]:
        """
        Переименовать символ.
        
        Args:
            file_path: Путь к файлу
            line: Строка (0-based)
            character: Символ (0-based)
            new_name: Новое имя
        
        Returns:
            Workspace edit: {file_path: [edits]}
        """
        return await self.lsp_client.rename_symbol(
            file_path, line, character, new_name
        )
    
    async def apply_rename(
        self,
        workspace_edit: dict[str, list[dict]],
    ) -> None:
        """
        Применить переименование к файлам.
        
        Args:
            workspace_edit: Результат rename
        """
        for file_path, edits in workspace_edit.items():
            content = await self._read_file(file_path)
            
            # Применить edits в обратном порядке (чтобы не сдвигать строки)
            edits.sort(key=lambda e: e["range"]["start"]["line"], reverse=True)
            
            for edit in edits:
                start_line = edit["range"]["start"]["line"]
                end_line = edit["range"]["end"]["line"]
                new_text = edit["newText"]
                
                lines = content.split('\n')
                lines[start_line:end_line + 1] = [new_text]
                content = '\n'.join(lines)
            
            await self._write_file(file_path, content)
```

---

## Интеграция с ContextManager

```python
class ContextManager:
    def __init__(
        self,
        definition_resolver: DefinitionResolver,
        reference_resolver: ReferenceResolver,
        ...
    ):
        self.definition_resolver = definition_resolver
        self.reference_resolver = reference_resolver
    
    async def build_context(self, session, task):
        # 1. Найти символы упомянутые в задаче
        symbols = self._extract_symbols_from_task(task)
        
        # 2. Для каждого символа найти определение и ссылки
        symbol_context = []
        for symbol_name in symbols:
            # Найти определение
            definitions = await self.definition_resolver.resolve_symbol(
                symbol_name, main_file
            )
            
            # Найти ссылки
            references = await self.reference_resolver.find_all_uses(
                symbol_name, main_file
            )
            
            symbol_context.append({
                "name": symbol_name,
                "definitions": definitions,
                "references": references
            })
        
        # 3. Добавить в контекст
        context = [self._format_symbol_context(symbol_context)]
        
        return context + other_context
```

---

## Roadmap реализации

### Phase 5: Базовая реализация (4 недели)

**Задачи:**
- [ ] Реализовать `LSPClient` с базовыми методами
- [ ] Реализовать `DefinitionResolver`
- [ ] Реализовать `ReferenceResolver`
- [ ] Unit tests

**Результат:** Базовая LSP интеграция.

### Phase 5: Расширенная реализация (2 недели)

**Задачи:**
- [ ] Реализовать `RenameEngine`
- [ ] Поддержка нескольких языков
- [ ] Интеграция с ContextManager
- [ ] Integration tests

**Результат:** Полная LSP интеграция.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы
- [Semantic Layer](./SEMANTIC_LAYER.md) — семантический уровень
