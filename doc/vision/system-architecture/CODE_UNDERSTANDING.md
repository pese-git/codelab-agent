# Code Understanding — Понимание кода

> Компоненты для глубокого понимания кодовой базы: индексация, символы, ссылки

## Оглавление

- [Обзор](#обзор)
- [CodeIndexer](#codeindexer)
- [SymbolIndex](#symbolindex)
- [ReferenceIndex](#referenceindex)
- [CrossFileAnalyzer](#crossfileanalyzer)
- [Интеграция с ContextManager](#интеграция-с-contextmanager)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

Code Understanding отвечает за **глубокое понимание кодовой базы**: индексация кода, поиск символов, анализ ссылок, межфайловый анализ.

**Компоненты:**
- `CodeIndexer` — индексация кодовой базы
- `SymbolIndex` — индекс символов (классы, функции, интерфейсы)
- `ReferenceIndex` — индекс ссылок (использование символов)
- `CrossFileAnalyzer` — межфайловый анализ

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ContextManager                                              │
│  └─ CodeIndexer         ← Code Understanding                 │
│  └─ SymbolIndex         ← Code Understanding                 │
│  └─ ReferenceIndex      ← Code Understanding                 │
│  └─ CrossFileAnalyzer   ← Code Understanding                 │
└─────────────────────────────────────────────────────────────┘
```

### Обоснование подхода

**Почему собственный CodeIndexer, а не tree-sitter/LSP напрямую?**

Tree-sitter и LSP дают точный AST-парсинг, но:
- **Tree-sitter** — требует бинарных зависимостей для каждого языка, усложняет деплой
- **LSP** — требует запуска language server для каждого языка, избыточен для индексации
- **Оба** — сложны в интеграции, требуют специализированных знаний

Собственный CodeIndexer:
- **Простота** — regex-based парсинг для базовых случаев (импорты, определения)
- **Лёгкость** — не требует внешних зависимостей
- **Расширяемость** — можно добавить tree-sitter/LSP позже для углублённого анализа

CodeIndexer — это MVP, который покрывает 80% случаев. Для оставшихся 20% можно интегрировать tree-sitter/LSP.

**Почему SymbolIndex — отдельный от CodeIndexer?**

Разделение ответственности:
- **CodeIndexer** — индексация файлов (структура, импорты, метаданные)
- **SymbolIndex** — индекс символов (классы, функции, интерфейсы с сигнатурами)

SymbolIndex решает другую задачу:
- Поиск символов по имени
- Получение сигнатур и docstrings
- Понимание типов (class, function, interface, variable)

Объединение нарушило бы SRP и усложнило бы тестирование.

**Почему ReferenceIndex использует git grep, а не AST?**

ReferenceIndex отслеживает, где используются символы. Подходы:
- **AST-based** — точный, но требует полного парсинга всех файлов
- **git grep** — быстрый, работает без парсинга, покрывает 90% случаев

git grep:
- **Быстро** — работает за миллисекунды даже на больших репозиториях
- **Просто** — не требует парсинга AST
- **Достаточно** — для большинства случаев (поиск использования функции)

Для случаев, когда нужна точность (например, различение overload'ов), можно добавить AST-based анализ позже.

**Почему CrossFileAnalyzer — отдельный компонент?**

CrossFileAnalyzer решает задачу, которую не решают другие компоненты:
- **CodeIndexer** — индексирует файлы
- **SymbolIndex** — индексирует символы
- **ReferenceIndex** — индексирует ссылки

CrossFileAnalyzer анализирует связи между файлами:
- Какие символы используются в каких файлах
- Какие файлы зависят от каких
- Какие символы не используются (dead code)
- Какие зависимости циклические

Это даёт LLM понимание архитектуры проекта, а не просто список файлов и символов.

**Альтернативы:**
- ❌ Tree-sitter/LSP напрямую — сложно интегрировать, требует внешних зависимостей
- ❌ Один универсальный индекс — нарушение SRP, сложно тестировать
- ❌ AST-based reference tracking — медленно, требует полного парсинга

---

## CodeIndexer

### Назначение

Индексация кодовой базы для быстрого поиска и анализа.

### Интерфейс

```python
@dataclass
class CodeIndex:
    """Индекс кодовой базы."""
    project_path: str
    files: dict[str, FileIndex]
    symbols: dict[str, list[SymbolInfo]]
    last_indexed: datetime

@dataclass
class FileIndex:
    """Индекс файла."""
    file_path: str
    language: str
    size_bytes: int
    line_count: int
    symbols: list[str]
    imports: list[str]
    last_modified: datetime

@dataclass
class SymbolInfo:
    """Информация о символе."""
    name: str
    kind: Literal["class", "function", "interface", "type", "variable"]
    file_path: str
    line_number: int
    signature: str
    docstring: str | None

class CodeIndexer:
    """Индексация кодовой базы."""
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        project_discovery: ProjectDiscovery,
    ):
        self.tools = tool_registry
        self.discovery = project_discovery
        self.index: CodeIndex | None = None
    
    async def index_project(self, cwd: str) -> CodeIndex:
        """
        Проиндексировать весь проект.
        
        Pipeline:
        1. Получить список файлов
        2. Для каждого файла извлечь символы
        3. Построить индекс
        """
        structure = await self.discovery.discover(cwd)
        
        # Получить список файлов
        files = await self._get_all_files(cwd, structure)
        
        # Индексировать каждый файл
        file_indices = {}
        all_symbols = {}
        
        for file_path in files:
            file_index = await self._index_file(file_path, structure.language)
            file_indices[file_path] = file_index
            
            # Добавить символы в общий индекс
            for symbol_name in file_index.symbols:
                if symbol_name not in all_symbols:
                    all_symbols[symbol_name] = []
                all_symbols[symbol_name].append(file_path)
        
        self.index = CodeIndex(
            project_path=cwd,
            files=file_indices,
            symbols=all_symbols,
            last_indexed=datetime.now()
        )
        
        return self.index
    
    async def _get_all_files(
        self,
        cwd: str,
        structure: ProjectStructure,
    ) -> list[str]:
        """Получить список всех файлов."""
        extensions = {
            "typescript": [".ts", ".tsx"],
            "python": [".py"],
            "go": [".go"],
        }
        
        exts = extensions.get(structure.language, [])
        
        result = await self.tools.execute(
            "terminal/create",
            {"command": f"find . -type f \\( {' -o '.join([f'-name \"*{ext}\"' for ext in exts])} \\)", "cwd": cwd}
        )
        
        return [f for f in result.output.strip().split('\n') if f]
    
    async def _index_file(
        self,
        file_path: str,
        language: str,
    ) -> FileIndex:
        """Индексировать файл."""
        content = await self._read_file(file_path)
        
        # Извлечь символы
        symbols = self._extract_symbols(content, language)
        
        # Извлечь импорты
        imports = self._extract_imports(content, language)
        
        return FileIndex(
            file_path=file_path,
            language=language,
            size_bytes=len(content.encode()),
            line_count=len(content.split('\n')),
            symbols=symbols,
            imports=imports,
            last_modified=datetime.now()
        )
    
    def _extract_symbols(self, content: str, language: str) -> list[str]:
        """Извлечь символы из файла."""
        symbols = []
        
        if language == "typescript":
            # Классы
            symbols.extend(re.findall(r'class\s+(\w+)', content))
            # Функции
            symbols.extend(re.findall(r'function\s+(\w+)', content))
            # Интерфейсы
            symbols.extend(re.findall(r'interface\s+(\w+)', content))
            # Типы
            symbols.extend(re.findall(r'type\s+(\w+)', content))
        
        elif language == "python":
            # Классы
            symbols.extend(re.findall(r'class\s+(\w+)', content))
            # Функции
            symbols.extend(re.findall(r'def\s+(\w+)', content))
        
        elif language == "go":
            # Функции
            symbols.extend(re.findall(r'func\s+(\w+)', content))
            # Структуры
            symbols.extend(re.findall(r'type\s+(\w+)\s+struct', content))
        
        return symbols
    
    def _extract_imports(self, content: str, language: str) -> list[str]:
        """Извлечь импорты из файла."""
        imports = []
        
        if language == "typescript":
            imports.extend(re.findall(r"import\s+.+\s+from\s+['\"]([^'\"]+)['\"]", content))
        
        elif language == "python":
            imports.extend(re.findall(r'^from\s+([\w.]+)\s+import', content, re.MULTILINE))
            imports.extend(re.findall(r'^import\s+([\w.]+)', content, re.MULTILINE))
        
        elif language == "go":
            imports.extend(re.findall(r'import\s+"([^"]+)"', content))
        
        return imports
```

---

## SymbolIndex

### Назначение

Индекс символов: классы, функции, интерфейсы с их сигнатурами и документацией.

### Интерфейс

```python
class SymbolIndex:
    """Индекс символов."""
    
    def __init__(self, code_indexer: CodeIndexer):
        self.code_indexer = code_indexer
        self.symbols: dict[str, list[SymbolInfo]] = {}
    
    async def build_index(self, cwd: str) -> None:
        """Построить индекс символов."""
        index = await self.code_indexer.index_project(cwd)
        
        for file_path, file_index in index.files.items():
            content = await self._read_file(file_path)
            symbols = self._extract_detailed_symbols(content, file_index.language, file_path)
            
            for symbol in symbols:
                if symbol.name not in self.symbols:
                    self.symbols[symbol.name] = []
                self.symbols[symbol.name].append(symbol)
    
    def _extract_detailed_symbols(
        self,
        content: str,
        language: str,
        file_path: str,
    ) -> list[SymbolInfo]:
        """Извлечь детальные символы с сигнатурами."""
        symbols = []
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            # Классы
            match = re.match(r'(?:export\s+)?class\s+(\w+)', line)
            if match:
                symbols.append(SymbolInfo(
                    name=match.group(1),
                    kind="class",
                    file_path=file_path,
                    line_number=i + 1,
                    signature=line.strip(),
                    docstring=self._extract_docstring(lines, i)
                ))
            
            # Функции
            match = re.match(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)', line)
            if match:
                symbols.append(SymbolInfo(
                    name=match.group(1),
                    kind="function",
                    file_path=file_path,
                    line_number=i + 1,
                    signature=line.strip(),
                    docstring=self._extract_docstring(lines, i)
                ))
            
            # Интерфейсы
            match = re.match(r'(?:export\s+)?interface\s+(\w+)', line)
            if match:
                symbols.append(SymbolInfo(
                    name=match.group(1),
                    kind="interface",
                    file_path=file_path,
                    line_number=i + 1,
                    signature=line.strip(),
                    docstring=None
                ))
        
        return symbols
    
    def find_symbol(self, name: str) -> list[SymbolInfo]:
        """Найти символ по имени."""
        return self.symbols.get(name, [])
    
    def find_symbols_by_kind(
        self,
        kind: Literal["class", "function", "interface"],
    ) -> list[SymbolInfo]:
        """Найти символы по типу."""
        result = []
        for symbols in self.symbols.values():
            result.extend([s for s in symbols if s.kind == kind])
        return result
```

---

## ReferenceIndex

### Назначение

Индекс ссылок: где используются символы.

### Интерфейс

```python
@dataclass
class Reference:
    """Ссылка на символ."""
    file_path: str
    line_number: int
    context: str  # Строка с использованием

class ReferenceIndex:
    """Индекс ссылок."""
    
    def __init__(self, symbol_index: SymbolIndex):
        self.symbol_index = symbol_index
        self.references: dict[str, list[Reference]] = {}
    
    async def build_index(self, cwd: str) -> None:
        """Построить индекс ссылок."""
        # Получить все символы
        all_symbols = list(self.symbol_index.symbols.keys())
        
        # Для каждого символа найти все использования
        for symbol_name in all_symbols:
            refs = await self._find_references(cwd, symbol_name)
            self.references[symbol_name] = refs
    
    async def _find_references(
        self,
        cwd: str,
        symbol_name: str,
    ) -> list[Reference]:
        """Найти все использования символа."""
        # Использовать git grep для поиска
        result = await self.tools.execute(
            "terminal/create",
            {"command": f"git grep -n '{symbol_name}'", "cwd": cwd}
        )
        
        refs = []
        for line in result.output.strip().split('\n'):
            if not line:
                continue
            parts = line.split(':', 2)
            if len(parts) >= 3:
                refs.append(Reference(
                    file_path=parts[0],
                    line_number=int(parts[1]),
                    context=parts[2]
                ))
        
        return refs
    
    def get_references(self, symbol_name: str) -> list[Reference]:
        """Получить все ссылки на символ."""
        return self.references.get(symbol_name, [])
    
    def get_reference_count(self, symbol_name: str) -> int:
        """Получить количество ссылок на символ."""
        return len(self.references.get(symbol_name, []))
```

---

## CrossFileAnalyzer

### Назначение

Межфайловый анализ: понимание связей между файлами.

### Интерфейс

```python
class CrossFileAnalyzer:
    """Межфайловый анализ."""
    
    def __init__(
        self,
        symbol_index: SymbolIndex,
        reference_index: ReferenceIndex,
    ):
        self.symbol_index = symbol_index
        self.reference_index = reference_index
    
    async def analyze_symbol_usage(self, symbol_name: str) -> dict[str, Any]:
        """
        Анализировать использование символа.
        
        Returns:
            {
                "definition": SymbolInfo,
                "references": list[Reference],
                "imported_by": list[str],
                "usage_count": int
            }
        """
        # Найти определение
        definitions = self.symbol_index.find_symbol(symbol_name)
        if not definitions:
            return {"error": f"Symbol {symbol_name} not found"}
        
        definition = definitions[0]
        
        # Найти все ссылки
        references = self.reference_index.get_references(symbol_name)
        
        # Найти файлы, которые импортируют этот символ
        imported_by = list(set([ref.file_path for ref in references]))
        
        return {
            "definition": definition,
            "references": references,
            "imported_by": imported_by,
            "usage_count": len(references)
        }
    
    async def find_unused_symbols(self) -> list[SymbolInfo]:
        """Найти неиспользуемые символы."""
        unused = []
        
        for symbol_name, symbols in self.symbol_index.symbols.items():
            refs = self.reference_index.get_references(symbol_name)
            
            # Если символ определён, но не используется (кроме определения)
            if len(refs) <= len(symbols):
                unused.extend(symbols)
        
        return unused
    
    async def find_circular_dependencies(self) -> list[list[str]]:
        """Найти циклические зависимости между файлами."""
        # Построить граф импортов
        import_graph = await self._build_import_graph()
        
        # Найти циклы
        cycles = self._find_cycles(import_graph)
        
        return cycles
```

---

## Интеграция с ContextManager

```python
class ContextManager:
    def __init__(
        self,
        symbol_index: SymbolIndex,
        reference_index: ReferenceIndex,
        cross_file_analyzer: CrossFileAnalyzer,
        ...
    ):
        self.symbol_index = symbol_index
        self.reference_index = reference_index
        self.cross_file_analyzer = cross_file_analyzer
    
    async def build_context(self, session, task):
        # 1. Найти символы упомянутые в задаче
        symbols = self._extract_symbols_from_task(task)
        
        # 2. Для каждого символа найти определение и использования
        symbol_context = []
        for symbol_name in symbols:
            usage = await self.cross_file_analyzer.analyze_symbol_usage(symbol_name)
            symbol_context.append(usage)
        
        # 3. Добавить в контекст
        context = [self._format_symbol_context(symbol_context)]
        
        return context + other_context
```

---

## Roadmap реализации

### Phase 4: Базовая реализация (3 недели)

**Задачи:**
- [ ] Реализовать `CodeIndexer` с индексацией файлов
- [ ] Реализовать `SymbolIndex` с извлечением символов
- [ ] Реализовать `ReferenceIndex` с поиском ссылок
- [ ] Unit tests

**Результат:** Базовое понимание кодовой базы.

### Phase 4: Расширенная реализация (2 недели)

**Задачи:**
- [ ] Реализовать `CrossFileAnalyzer` с межфайловым анализом
- [ ] Реализовать поиск неиспользуемых символов
- [ ] Реализовать поиск циклических зависимостей
- [ ] Интеграция с ContextManager
- [ ] Integration tests

**Результат:** Полное понимание кодовой базы.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы
- [Planning Engine](./PLANNING_ENGINE.md) — движок планирования
