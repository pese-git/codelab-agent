# Autonomous Reasoning — Автономное рассуждение

> Компоненты для автономного рассуждения: рефлексия, самокритика, исправление ошибок

## Оглавление

- [Обзор](#обзор)
- [ReflectionEngine](#reflectionengine)
- [SelfCritiqueEngine](#selfcritiqueengine)
- [RepairEngine](#repairengine)
- [Интеграция с ExecutionEngine](#интеграция-с-executionengine)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

Autonomous Reasoning отвечает за **автономное рассуждение**: рефлексия над результатами, самокритика, автоматическое исправление ошибок.

**Компоненты:**
- `ReflectionEngine` — движок рефлексии (анализ результатов)
- `SelfCritiqueEngine` — движок самокритики (поиск ошибок в своих решениях)
- `RepairEngine` — движок исправления (автоматическое исправление ошибок)

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ExecutionEngine                                             │
│  └─ ReflectionEngine      ← Autonomous Reasoning             │
│  └─ SelfCritiqueEngine    ← Autonomous Reasoning             │
│  └─ RepairEngine          ← Autonomous Reasoning             │
└─────────────────────────────────────────────────────────────┘
```

---

## ReflectionEngine

### Назначение

Движок рефлексии: анализ результатов выполнения, понимание что получилось, что нет.

### Интерфейс

```python
@dataclass
class Reflection:
    """Результат рефлексии."""
    task: str
    success: bool
    what_went_well: list[str]
    what_went_wrong: list[str]
    lessons_learned: list[str]
    confidence: float  # 0.0 - 1.0

class ReflectionEngine:
    """Движок рефлексии."""
    
    def __init__(self, llm: LLMProvider):
        self.llm = llm
    
    async def reflect(
        self,
        task: str,
        execution_result: ExecutionResult,
        context: dict[str, Any],
    ) -> Reflection:
        """
        Рефлексия над результатом выполнения.
        
        Args:
            task: Исходная задача
            execution_result: Результат выполнения
            context: Контекст выполнения
        
        Returns:
            Reflection с анализом
        """
        prompt = f"""
Reflect on the execution of this task.

Task: {task}

Execution result:
- Success: {execution_result.success}
- Output: {execution_result.output}
- Errors: {execution_result.errors}

Context:
- Files modified: {context.get('files_modified', [])}
- Tests run: {context.get('tests_run', 0)}
- Tests passed: {context.get('tests_passed', 0)}

Analyze:
1. What went well?
2. What went wrong?
3. What lessons can be learned?
4. How confident are you in the result (0.0-1.0)?

Return JSON:
{{
    "success": true/false,
    "what_went_well": ["..."],
    "what_went_wrong": ["..."],
    "lessons_learned": ["..."],
    "confidence": 0.0-1.0
}}
"""
        
        response = await self.llm.create_completion(
            CompletionRequest(
                model="openai/gpt-4o",
                messages=[LLMMessage(role="user", content=prompt)],
                max_tokens=1000,
                temperature=0.0,
            )
        )
        
        return self._parse_reflection(response.text, task)
    
    def _parse_reflection(self, text: str, task: str) -> Reflection:
        """Парсить рефлексию из LLM ответа."""
        import json
        data = json.loads(text)
        
        return Reflection(
            task=task,
            success=data["success"],
            what_went_well=data.get("what_went_well", []),
            what_went_wrong=data.get("what_went_wrong", []),
            lessons_learned=data.get("lessons_learned", []),
            confidence=data.get("confidence", 0.5)
        )
```

---

## SelfCritiqueEngine

### Назначение

Движок самокритики: поиск ошибок в своих решениях до выполнения.

### Интерфейс

```python
@dataclass
class Critique:
    """Результат самокритики."""
    proposed_solution: str
    issues: list[Issue]
    suggestions: list[str]
    should_proceed: bool  # Стоит ли выполнять решение

@dataclass
class Issue:
    """Проблема в решении."""
    severity: Literal["low", "medium", "high"]
    description: str
    location: str | None  # Файл или модуль

class SelfCritiqueEngine:
    """Движок самокритики."""
    
    def __init__(self, llm: LLMProvider):
        self.llm = llm
    
    async def critique(
        self,
        task: str,
        proposed_solution: str,
        context: dict[str, Any],
    ) -> Critique:
        """
        Самокритика предложенного решения.
        
        Args:
            task: Исходная задача
            proposed_solution: Предложенное решение
            context: Контекст задачи
        
        Returns:
            Critique с анализом
        """
        prompt = f"""
Critique this proposed solution before execution.

Task: {task}

Proposed solution:
{proposed_solution}

Context:
- Project: {context.get('project_info', {})}
- Related files: {context.get('related_files', [])}
- Dependencies: {context.get('dependencies', [])}

Analyze:
1. What issues might this solution have?
2. What could go wrong?
3. Are there edge cases not covered?
4. Should we proceed with this solution?

Return JSON:
{{
    "issues": [
        {{
            "severity": "low|medium|high",
            "description": "...",
            "location": "..."
        }}
    ],
    "suggestions": ["..."],
    "should_proceed": true/false
}}
"""
        
        response = await self.llm.create_completion(
            CompletionRequest(
                model="openai/gpt-4o",
                messages=[LLMMessage(role="user", content=prompt)],
                max_tokens=1000,
                temperature=0.0,
            )
        )
        
        return self._parse_critique(response.text, proposed_solution)
    
    def _parse_critique(self, text: str, proposed_solution: str) -> Critique:
        """Парсить критику из LLM ответа."""
        import json
        data = json.loads(text)
        
        issues = [
            Issue(
                severity=issue["severity"],
                description=issue["description"],
                location=issue.get("location")
            )
            for issue in data.get("issues", [])
        ]
        
        return Critique(
            proposed_solution=proposed_solution,
            issues=issues,
            suggestions=data.get("suggestions", []),
            should_proceed=data.get("should_proceed", True)
        )
```

---

## RepairEngine

### Назначение

Движок исправления: автоматическое исправление ошибок на основе рефлексии и критики.

### Интерфейс

```python
@dataclass
class RepairAction:
    """Действие по исправлению."""
    action_type: Literal["modify_file", "run_command", "retry_task"]
    description: str
    file_path: str | None
    code_changes: dict[str, str] | None  # {file_path: new_content}
    command: str | None

class RepairEngine:
    """Движок исправления."""
    
    def __init__(
        self,
        llm: LLMProvider,
        reflection_engine: ReflectionEngine,
        self_critique_engine: SelfCritiqueEngine,
    ):
        self.llm = llm
        self.reflection_engine = reflection_engine
        self.self_critique_engine = self_critique_engine
    
    async def repair(
        self,
        task: str,
        failed_result: ExecutionResult,
        reflection: Reflection,
        context: dict[str, Any],
    ) -> list[RepairAction]:
        """
        Сгенерировать действия по исправлению.
        
        Args:
            task: Исходная задача
            failed_result: Результат неудачного выполнения
            reflection: Рефлексия над результатом
            context: Контекст задачи
        
        Returns:
            Список действий по исправлению
        """
        prompt = f"""
Generate repair actions based on the reflection.

Task: {task}

Failed result:
- Errors: {failed_result.errors}
- Output: {failed_result.output}

Reflection:
- What went wrong: {reflection.what_went_wrong}
- Lessons learned: {reflection.lessons_learned}

Context:
- Files modified: {context.get('files_modified', [])}
- Test failures: {context.get('test_failures', [])}

Generate repair actions:
1. What files need to be modified?
2. What commands need to be run?
3. Should we retry the task?

Return JSON:
{{
    "actions": [
        {{
            "action_type": "modify_file|run_command|retry_task",
            "description": "...",
            "file_path": "...",
            "code_changes": {{"file_path": "new_content"}},
            "command": "..."
        }}
    ]
}}
"""
        
        response = await self.llm.create_completion(
            CompletionRequest(
                model="openai/gpt-4o",
                messages=[LLMMessage(role="user", content=prompt)],
                max_tokens=2000,
                temperature=0.0,
            )
        )
        
        return self._parse_repair_actions(response.text)
    
    def _parse_repair_actions(self, text: str) -> list[RepairAction]:
        """Парсить действия по исправлению из LLM ответа."""
        import json
        data = json.loads(text)
        
        return [
            RepairAction(
                action_type=action["action_type"],
                description=action["description"],
                file_path=action.get("file_path"),
                code_changes=action.get("code_changes"),
                command=action.get("command")
            )
            for action in data.get("actions", [])
        ]
    
    async def apply_repair_actions(
        self,
        actions: list[RepairAction],
    ) -> ExecutionResult:
        """
        Применить действия по исправлению.
        
        Args:
            actions: Список действий
        
        Returns:
            Результат применения
        """
        results = []
        
        for action in actions:
            if action.action_type == "modify_file":
                # Применить изменения к файлам
                for file_path, new_content in action.code_changes.items():
                    await self._write_file(file_path, new_content)
                results.append(f"Modified files: {list(action.code_changes.keys())}")
            
            elif action.action_type == "run_command":
                # Выполнить команду
                result = await self._run_command(action.command)
                results.append(f"Command result: {result}")
            
            elif action.action_type == "retry_task":
                # Повторить задачу
                results.append("Retrying task...")
        
        return ExecutionResult(
            success=True,
            output='\n'.join(results),
            errors=[]
        )
```

---

## Интеграция с ExecutionEngine

```python
class ExecutionEngine:
    def __init__(
        self,
        reflection_engine: ReflectionEngine,
        self_critique_engine: SelfCritiqueEngine,
        repair_engine: RepairEngine,
        ...
    ):
        self.reflection_engine = reflection_engine
        self.self_critique_engine = self_critique_engine
        self.repair_engine = repair_engine
    
    async def execute_with_autonomous_reasoning(self, session, task):
        max_retries = 3
        
        for attempt in range(max_retries):
            # 1. Выполнить задачу
            result = await self.execute(session, task)
            
            if result.success:
                # 2. Рефлексия над успешным результатом
                reflection = await self.reflection_engine.reflect(
                    task, result, context
                )
                
                # Сохранить уроки в память
                await self._save_lessons(reflection.lessons_learned)
                
                return result
            
            else:
                # 3. Рефлексия над неудачным результатом
                reflection = await self.reflection_engine.reflect(
                    task, result, context
                )
                
                # 4. Сгенерировать действия по исправлению
                repair_actions = await self.repair_engine.repair(
                    task, result, reflection, context
                )
                
                # 5. Применить действия
                await self.repair_engine.apply_repair_actions(repair_actions)
                
                # 6. Продолжить цикл
        
        return ExecutionResult(
            success=False,
            error=f"Failed after {max_retries} attempts"
        )
    
    async def execute_with_self_critique(self, session, task):
        # 1. Сгенерировать решение
        proposed_solution = await self._generate_solution(task)
        
        # 2. Самокритика
        critique = await self.self_critique_engine.critique(
            task, proposed_solution, context
        )
        
        if not critique.should_proceed:
            # 3. Если есть серьёзные проблемы — пересмотреть решение
            revised_solution = await self._revise_solution(
                task, proposed_solution, critique
            )
            
            # 4. Повторная самокритика
            critique = await self.self_critique_engine.critique(
                task, revised_solution, context
            )
        
        # 5. Выполнить решение
        return await self.execute(session, task)
```

---

## Roadmap реализации

### Phase 5: Базовая реализация (4 недели)

**Задачи:**
- [ ] Реализовать `ReflectionEngine` с базовой рефлексией
- [ ] Реализовать `SelfCritiqueEngine` с самокритикой
- [ ] Unit tests

**Результат:** Базовое автономное рассуждение.

### Phase 5: Расширенная реализация (2 недели)

**Задачи:**
- [ ] Реализовать `RepairEngine` с исправлением ошибок
- [ ] Реализовать цикл retry с рефлексией
- [ ] Интеграция с ExecutionEngine
- [ ] Integration tests

**Результат:** Полное автономное рассуждение с исправлением.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы
- [Planning Engine](./PLANNING_ENGINE.md) — движок планирования
