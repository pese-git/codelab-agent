# File Intelligence — Интеллектуальная работа с файлами

> Компоненты для умного чтения и обработки файлов

## Оглавление

- [Обзор](#обзор)
- [ReadRangeStrategy](#readrangestrategy)
- [LargeFileHandler](#largefilehandler)
- [ContextPruner](#contextpruner)
- [Интеграция с ContextGatherer](#интеграция-с-contextgatherer)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

File Intelligence отвечает за **интеллектуальную работу с файлами**: чтение диапазонов, обработку больших файлов, обрезку нерелевантного контекста.

**Компоненты:**
- `ReadRangeStrategy` — стратегия чтения диапазонов файлов
- `LargeFileHandler` — обработка больших файлов
- `ContextPruner` — обрезка нерелевантного контекста

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ContextManager                                              │
│  └─ ContextGatherer                                          │
│      ├─ ReadRangeStrategy  ← File Intelligence               │
│      ├─ LargeFileHandler   ← File Intelligence               │
│      └─ ContextPruner      ← File Intelligence               │
└─────────────────────────────────────────────────────────────┘
```

---

## ReadRangeStrategy

### Назначение

Стратегия чтения диапазонов файлов. Вместо чтения всего файла читает только релевантные части.

**Зачем нужно:**
- Большие файлы (1000+ строк) не нужно читать целиком
- LLM нужны только релевантные части
- Экономия токенов: 30-50%

### Интерфейс

```python
@dataclass
class ReadRange:
    """Диапазон чтения файла."""
    file_path: str
    start_line: int
    end_line: int
    reason: str  # Почему читаем этот диапазон

@dataclass
class FileSnippet:
    """Фрагмент файла."""
    file_path: str
    start_line: int
    end_line: int
    content: str
    context_before: str  # 10 строк до
    context_after: str   # 10 строк после

class ReadRangeStrategy:
    """Стратегия чтения диапазонов файлов."""
    
    def __init__(self, tool_registry: ToolRegistry):
        self.tools = tool_registry
    
    async def read_range(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        context_lines: int = 10,
    ) -> FileSnippet:
        """
        Прочитать диапазон файла с контекстом.
        
        Args:
            file_path: Путь к файлу
            start_line: Начальная строка (1-based)
            end_line: Конечная строка (1-based)
            context_lines: Количество строк контекста до/после
        
        Returns:
            FileSnippet с содержимым и контекстом
        """
        # Читать основной диапазон
        main_content = await self._read_lines(
            file_path, start_line, end_line
        )
        
        # Читать контекст до
        context_start = max(1, start_line - context_lines)
        context_before = await self._read_lines(
            file_path, context_start, start_line - 1
        )
        
        # Читать контекст после
        context_after = await self._read_lines(
            file_path, end_line + 1, end_line + context_lines
        )
        
        return FileSnippet(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            content=main_content,
            context_before=context_before,
            context_after=context_after
        )
    
    async def read_smart(
        self,
        file_path: str,
        target_lines: list[int],
        context_lines: int = 10,
    ) -> list[FileSnippet]:
        """
        Умное чтение: объединить близкие диапазоны.
        
        Если target_lines = [10, 11, 12, 50, 51, 52]
        То читаем два диапазона: [10-12] и [50-52]
        """
        # Группировать близкие строки
        ranges = self._group_consecutive_lines(target_lines)
        
        # Прочитать каждый диапазон
        snippets = []
        for start, end in ranges:
            snippet = await self.read_range(
                file_path, start, end, context_lines
            )
            snippets.append(snippet)
        
        return snippets
    
    def _group_consecutive_lines(
        self,
        lines: list[int],
        max_gap: int = 5,
    ) -> list[tuple[int, int]]:
        """
        Группировать близкие строки в диапазоны.
        
        [10, 11, 12, 50, 51, 52] → [(10, 12), (50, 52)]
        """
        if not lines:
            return []
        
        lines = sorted(lines)
        ranges = []
        start = lines[0]
        end = lines[0]
        
        for line in lines[1:]:
            if line - end <= max_gap:
                end = line
            else:
                ranges.append((start, end))
                start = line
                end = line
        
        ranges.append((start, end))
        return ranges
    
    async def _read_lines(
        self,
        file_path: str,
        start: int,
        end: int,
    ) -> str:
        """Прочитать строки файла."""
        result = await self.tools.execute(
            "fs/read_text_file",
            {
                "path": file_path,
                "line": start,
                "limit": end - start + 1
            }
        )
        return result.content
```

### Пример использования

```python
strategy = ReadRangeStrategy(tool_registry)

# Прочитать диапазон с контекстом
snippet = await strategy.read_range(
    file_path="src/auth.service.ts",
    start_line=50,
    end_line=60,
    context_lines=10
)

print(snippet.content)  # Строки 50-60
print(snippet.context_before)  # Строки 40-49
print(snippet.context_after)  # Строки 61-70

# Умное чтение: объединить близкие диапазоны
snippets = await strategy.read_smart(
    file_path="src/auth.service.ts",
    target_lines=[10, 11, 12, 50, 51, 52]
)

# Результат: два FileSnippet
# [10-12] с контекстом
# [50-52] с контекстом
```

---

## LargeFileHandler

### Назначение

Обработка больших файлов (1000+ строк). Вместо чтения всего файла:
1. Читает сигнатуры (imports, class/function signatures)
2. Читает только релевантные части
3. Суммаризирует нерелевантные части

### Интерфейс

```python
@dataclass
class FileSignature:
    """Сигнатура файла."""
    file_path: str
    total_lines: int
    imports: list[str]
    classes: list[str]
    functions: list[str]
    exports: list[str]

@dataclass
class LargeFileSummary:
    """Суммаризация большого файла."""
    file_path: str
    signature: FileSignature
    relevant_snippets: list[FileSnippet]
    summary: str  # LLM суммаризация нерелевантных частей

class LargeFileHandler:
    """Обработка больших файлов."""
    
    LARGE_FILE_THRESHOLD = 1000  # строк
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        read_strategy: ReadRangeStrategy,
        llm: LLMProvider,
    ):
        self.tools = tool_registry
        self.read_strategy = read_strategy
        self.llm = llm
    
    async def handle(
        self,
        file_path: str,
        relevant_lines: list[int] | None = None,
    ) -> str:
        """
        Обработать большой файл.
        
        Если файл < LARGE_FILE_THRESHOLD:
            Читать целиком
        
        Если файл >= LARGE_FILE_THRESHOLD:
            1. Извлечь сигнатуры
            2. Прочитать релевантные части
            3. Суммаризировать нерелевантные части
        """
        # Получить размер файла
        total_lines = await self._count_lines(file_path)
        
        if total_lines < self.LARGE_FILE_THRESHOLD:
            # Маленький файл — читать целиком
            return await self._read_full(file_path)
        
        # Большой файл — умная обработка
        signature = await self._extract_signature(file_path)
        
        if relevant_lines:
            # Прочитать релевантные части
            snippets = await self.read_strategy.read_smart(
                file_path, relevant_lines
            )
        else:
            # Прочитать только сигнатуры
            snippets = await self._read_signatures(file_path, signature)
        
        # Суммаризировать нерелевантные части
        summary = await self._summarize_irrelevant(
            file_path, signature, snippets
        )
        
        return self._format_output(signature, snippets, summary)
    
    async def _extract_signature(self, file_path: str) -> FileSignature:
        """Извлечь сигнатуры файла."""
        content = await self._read_full(file_path)
        total_lines = len(content.split('\n'))
        
        # Извлечь imports
        imports = self._extract_imports(content)
        
        # Извлечь классы
        classes = self._extract_classes(content)
        
        # Извлечь функции
        functions = self._extract_functions(content)
        
        # Извлечь exports
        exports = self._extract_exports(content)
        
        return FileSignature(
            file_path=file_path,
            total_lines=total_lines,
            imports=imports,
            classes=classes,
            functions=functions,
            exports=exports
        )
    
    def _extract_imports(self, content: str) -> list[str]:
        """Извлечь импорты."""
        # TypeScript: import X from 'Y'
        # Python: from X import Y, import X
        pattern = r'^(?:import|from)\s+.+$'
        return re.findall(pattern, content, re.MULTILINE)
    
    def _extract_classes(self, content: str) -> list[str]:
        """Извлечь классы."""
        # TypeScript: class X { ... }
        # Python: class X: ...
        pattern = r'^class\s+(\w+)'
        return re.findall(pattern, content, re.MULTILINE)
    
    def _extract_functions(self, content: str) -> list[str]:
        """Извлечь функции."""
        # TypeScript: function X() { ... }
        # Python: def X(): ...
        pattern = r'^(?:function|def|async function|async def)\s+(\w+)'
        return re.findall(pattern, content, re.MULTILINE)
    
    def _extract_exports(self, content: str) -> list[str]:
        """Извлечь exports."""
        pattern = r'^export\s+(?:default\s+)?(?:class|function|const|let|var)\s+(\w+)'
        return re.findall(pattern, content, re.MULTILINE)
    
    async def _summarize_irrelevant(
        self,
        file_path: str,
        signature: FileSignature,
        relevant_snippets: list[FileSnippet],
    ) -> str:
        """Суммаризировать нерелевантные части."""
        prompt = f"""
Summarize this file based on its signature.

File: {file_path}
Total lines: {signature.total_lines}

Imports:
{chr(10).join(signature.imports)}

Classes:
{chr(10).join(signature.classes)}

Functions:
{chr(10).join(signature.functions)}

Exports:
{chr(10).join(signature.exports)}

Provide a concise summary (2-3 sentences) of what this file does.
"""
        
        response = await self.llm.create_completion(
            CompletionRequest(
                model="openai/gpt-4o-mini",
                messages=[LLMMessage(role="user", content=prompt)],
                max_tokens=200,
                temperature=0.0,
            )
        )
        
        return response.text
    
    def _format_output(
        self,
        signature: FileSignature,
        snippets: list[FileSnippet],
        summary: str,
    ) -> str:
        """Форматировать вывод."""
        parts = []
        
        parts.append(f"# File: {signature.file_path}")
        parts.append(f"Total lines: {signature.total_lines}")
        parts.append("")
        
        parts.append("## Summary")
        parts.append(summary)
        parts.append("")
        
        parts.append("## Imports")
        parts.append('\n'.join(signature.imports))
        parts.append("")
        
        parts.append("## Classes")
        parts.append('\n'.join(signature.classes))
        parts.append("")
        
        parts.append("## Functions")
        parts.append('\n'.join(signature.functions))
        parts.append("")
        
        if snippets:
            parts.append("## Relevant Parts")
            for snippet in snippets:
                parts.append(f"### Lines {snippet.start_line}-{snippet.end_line}")
                if snippet.context_before:
                    parts.append("```")
                    parts.append(snippet.context_before)
                    parts.append("```")
                parts.append("```")
                parts.append(snippet.content)
                parts.append("```")
                if snippet.context_after:
                    parts.append("```")
                    parts.append(snippet.context_after)
                    parts.append("```")
                parts.append("")
        
        return '\n'.join(parts)
```

### Пример использования

```python
handler = LargeFileHandler(tool_registry, read_strategy, llm)

# Обработать большой файл
output = await handler.handle(
    file_path="src/large-service.ts",
    relevant_lines=[50, 51, 52]  # Только эти строки релевантны
)

print(output)
# # File: src/large-service.ts
# Total lines: 2500
#
# ## Summary
# This file implements a large authentication service with JWT token
# management, user validation, and session handling.
#
# ## Imports
# import { Injectable } from '@nestjs/common'
# import { JwtService } from '@nestjs/jwt'
# ...
#
# ## Classes
# AuthService
# TokenValidator
# ...
#
# ## Functions
# validateUser
# generateToken
# ...
#
# ## Relevant Parts
# ### Lines 50-52
# [context before]
# [content]
# [context after]
```

---

## ContextPruner

### Назначение

Обрезка нерелевантного контекста перед отправкой в LLM. Удаляет:
- Комментарии (если не релевантны)
- Пустые строки
- Дублирующийся код
- Нерелевантные импорты

### Интерфейс

```python
class ContextPruner:
    """Обрезка нерелевантного контекста."""
    
    def __init__(self, config: PrunerConfig | None = None):
        self.config = config or PrunerConfig()
    
    def prune(self, content: str, context: PruneContext) -> str:
        """
        Обрезать нерелевантный контекст.
        
        Args:
            content: Содержимое файла
            context: Контекст обрезки (какие части релевантны)
        
        Returns:
            Обрезанное содержимое
        """
        # Удалить комментарии (если не релевантны)
        if self.config.remove_comments:
            content = self._remove_comments(content, context)
        
        # Удалить пустые строки
        if self.config.remove_empty_lines:
            content = self._remove_empty_lines(content)
        
        # Удалить дублирующийся код
        if self.config.remove_duplicates:
            content = self._remove_duplicates(content)
        
        # Удалить нерелевантные импорты
        if self.config.remove_unused_imports:
            content = self._remove_unused_imports(content, context)
        
        return content
    
    def _remove_comments(self, content: str, context: PruneContext) -> str:
        """Удалить комментарии."""
        lines = content.split('\n')
        pruned = []
        
        for i, line in enumerate(lines):
            # Сохранить комментарии в релевантных диапазонах
            if self._is_in_relevant_range(i + 1, context.relevant_ranges):
                pruned.append(line)
                continue
            
            # Удалить однострочные комментарии
            if line.strip().startswith('//') or line.strip().startswith('#'):
                continue
            
            pruned.append(line)
        
        return '\n'.join(pruned)
    
    def _remove_empty_lines(self, content: str) -> str:
        """Удалить пустые строки."""
        lines = content.split('\n')
        pruned = [line for line in lines if line.strip()]
        return '\n'.join(pruned)
    
    def _remove_duplicates(self, content: str) -> str:
        """Удалить дублирующийся код."""
        lines = content.split('\n')
        seen = set()
        pruned = []
        
        for line in lines:
            if line.strip() and line not in seen:
                seen.add(line)
                pruned.append(line)
            elif not line.strip():
                pruned.append(line)
        
        return '\n'.join(pruned)
    
    def _remove_unused_imports(
        self,
        content: str,
        context: PruneContext,
    ) -> str:
        """Удалить неиспользуемые импорты."""
        lines = content.split('\n')
        pruned = []
        
        for line in lines:
            # Проверить является ли строка импортом
            if self._is_import(line):
                # Извлечь имя импорта
                import_name = self._extract_import_name(line)
                
                # Проверить используется ли импорт в релевантном коде
                if self._is_import_used(import_name, context.relevant_code):
                    pruned.append(line)
            else:
                pruned.append(line)
        
        return '\n'.join(pruned)
    
    def _is_import(self, line: str) -> bool:
        """Проверить является ли строка импортом."""
        return (
            line.strip().startswith('import ') or
            line.strip().startswith('from ') or
            line.strip().startswith('require(')
        )
    
    def _extract_import_name(self, line: str) -> str:
        """Извлечь имя импорта."""
        # import { X } from 'Y' → X
        # from X import Y → Y
        # const X = require('Y') → X
        
        match = re.search(r'import\s+{?\s*(\w+)', line)
        if match:
            return match.group(1)
        
        match = re.search(r'from\s+\w+\s+import\s+(\w+)', line)
        if match:
            return match.group(1)
        
        match = re.search(r'const\s+(\w+)\s*=\s*require', line)
        if match:
            return match.group(1)
        
        return ""
    
    def _is_import_used(self, import_name: str, code: str) -> bool:
        """Проверить используется ли импорт в коде."""
        return import_name in code
```

### Пример использования

```python
pruner = ContextPruner()

content = """
import { Injectable } from '@nestjs/common'
import { UnusedService } from './unused.service'

// This is a comment
export class AuthService {
    constructor(private jwtService: JwtService) {}
    
    // Another comment
    async validateUser(email: string) {
        return await this.userRepository.findByEmail(email)
    }
}
"""

context = PruneContext(
    relevant_ranges=[(5, 10)],  # Только строки 5-10 релевантны
    relevant_code="validateUser"
)

pruned = pruner.prune(content, context)

print(pruned)
# import { Injectable } from '@nestjs/common'
# export class AuthService {
#     constructor(private jwtService: JwtService) {}
#     async validateUser(email: string) {
#         return await this.userRepository.findByEmail(email)
#     }
# }
```

---

## Интеграция с ContextGatherer

```python
class ContextGatherer:
    def __init__(
        self,
        read_strategy: ReadRangeStrategy,
        large_file_handler: LargeFileHandler,
        context_pruner: ContextPruner,
        ...
    ):
        self.read_strategy = read_strategy
        self.large_file_handler = large_file_handler
        self.context_pruner = context_pruner
    
    async def gather_context(self, task, profile, session):
        # 1. Поиск релевантных файлов
        search_results = await self.search_engine.search(...)
        
        # 2. Чтение файлов
        file_contents = {}
        for file in candidate_files:
            # Получить релевантные строки
            relevant_lines = self._extract_relevant_lines(file, search_results)
            
            # Проверить размер файла
            total_lines = await self._count_lines(file)
            
            if total_lines > LargeFileHandler.LARGE_FILE_THRESHOLD:
                # Большой файл — умная обработка
                content = await self.large_file_handler.handle(
                    file, relevant_lines
                )
            else:
                # Маленький файл — чтение диапазонов
                if relevant_lines:
                    snippets = await self.read_strategy.read_smart(
                        file, relevant_lines
                    )
                    content = self._format_snippets(snippets)
                else:
                    content = await self.read_file(file)
            
            # 3. Обрезка нерелевантного контекста
            content = self.context_pruner.prune(content, prune_context)
            
            file_contents[file] = content
        
        return GatheredContext(...)
```

---

## Roadmap реализации

### Phase 2: Базовая реализация (1 неделя)

**Задачи:**
- [ ] Реализовать `ReadRangeStrategy.read_range()`
- [ ] Реализовать `read_smart()` с группировкой диапазонов
- [ ] Реализовать `LargeFileHandler.handle()`
- [ ] Реализовать `_extract_signature()`
- [ ] Unit tests

**Результат:** Базовое чтение диапазонов и обработка больших файлов.

### Phase 2: Расширенная реализация (1 неделя)

**Задачи:**
- [ ] Реализовать `ContextPruner.prune()`
- [ ] Реализовать удаление комментариев
- [ ] Реализовать удаление неиспользуемых импортов
- [ ] Интеграция с ContextGatherer
- [ ] Integration tests

**Результат:** Полная интеллектуальная работа с файлами.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы
- [Discovery Layer](./DISCOVERY_LAYER.md) — обнаружение и поиск
