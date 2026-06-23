# Planning Engine — Движок планирования

> Компоненты для планирования изменений и анализа влияния

## Оглавление

- [Обзор](#обзор)
- [PlanningEngine](#planningengine)
- [ModificationPlanner](#modificationplanner)
- [ChangeImpactAnalyzer](#changeimpactanalyzer)
- [Интеграция с ExecutionEngine](#интеграция-с-executionengine)
- [Roadmap реализации](#roadmap-реализации)

---

## Обзор

Planning Engine отвечает за **планирование изменений**: что нужно изменить, в каком порядке, какие файлы затронуты.

**Компоненты:**
- `PlanningEngine` — движок планирования
- `ModificationPlanner` — планировщик изменений
- `ChangeImpactAnalyzer` — анализ влияния изменений

**Место в архитектуре:**

```
┌─────────────────────────────────────────────────────────────┐
│  ExecutionEngine                                             │
│  └─ PlanningEngine         ← Planning Layer                  │
│  └─ ModificationPlanner    ← Planning Layer                  │
│  └─ ChangeImpactAnalyzer   ← Planning Layer                  │
└─────────────────────────────────────────────────────────────┘
```

### Обоснование подхода

**Почему LLM-based planning, а не rule-based?**

Rule-based planning (правила типа "если задача X, то сделай Y") имеет проблемы:
- **Негибкость** — нужно писать правила для каждого типа задач
- **Неполнота** — невозможно предвидеть все сценарии
- **Сложность поддержки** — правила конфликтуют друг с другом

LLM-based planning:
- **Гибкость** — LLM понимает контекст и адаптирует план
- **Универсальность** — работает для любых задач без написания правил
- **Понимание** — LLM учитывает зависимости, риски, порядок выполнения

LLM генерирует план на основе:
- Описания задачи
- Структуры проекта (из ContextGatherer)
- Графа зависимостей (из DependencyGraph)
- Примеров из памяти (из TaskMemory)

**Почему планировать вообще, а не просто действовать (agentic exploration)?**

Agentic exploration (действовать без плана) имеет проблемы:
- **Непредсказуемость** — агент может пойти не тем путём
- **Неэффективность** — много проб и ошибок
- **Отсутствие прозрачности** — пользователь не понимает, что делает агент

Planning:
- **Предсказуемость** — план показывает, что будет делать агент
- **Эффективность** — план минимизирует количество шагов
- **Прозрачность** — пользователь видит план и может его скорректировать
- **Контроль** — пользователь может одобрить/отклонить план до выполнения

**Почему ModificationPlanner — отдельный от PlanningEngine?**

Разделение ответственности:
- **PlanningEngine** — высокоуровневое планирование (разбиение задачи на шаги)
- **ModificationPlanner** — низкоуровневое планирование (конкретные изменения в файлах)

ModificationPlanner:
- Определяет, какие файлы нужно изменить
- Определяет, какие строки/функции нужно изменить
- Генерирует конкретные diff'ы

PlanningEngine:
- Разбивает задачу на шаги (например, "1. Добавить DTO, 2. Добавить сервис, 3. Добавить контроллер")
- Определяет порядок выполнения шагов
- Оценивает усилия и риски

Разделение позволяет:
- Тестировать каждый компонент независимо
- Переиспользовать ModificationPlanner для других задач
- Изменять логику планирования без изменения генерации diff'ов

**Почему ChangeImpactAnalyzer — отдельный компонент?**

ChangeImpactAnalyzer решает задачу, которую не решают другие компоненты:
- **PlanningEngine** — создаёт план
- **ModificationPlanner** — определяет изменения

ChangeImpactAnalyzer:
- Анализирует, какие файлы будут затронуты изменениями
- Определяет, какие тесты нужно запустить
- Оценивает риски (например, "изменение этого файла сломает 5 других файлов")

Это даёт:
- Понимание scope изменений
- Возможность отклонить рискованные изменения
- Автоматический запуск нужных тестов

**Альтернативы:**
- ❌ Rule-based planning — негибкий, сложно поддерживать
- ❌ Agentic exploration без плана — непредсказуемый, неэффективный
- ❌ Один универсальный планировщик — нарушение SRP, сложно тестировать

---

## PlanningEngine

### Назначение

Движок планирования: разбиение задачи на шаги, определение порядка выполнения.

### Интерфейс

```python
@dataclass
class Plan:
    """План выполнения задачи."""
    task: str
    steps: list[PlanStep]
    estimated_effort: str  # "low", "medium", "high"
    risks: list[str]

@dataclass
class PlanStep:
    """Шаг плана."""
    order: int
    description: str
    files_to_modify: list[str]
    dependencies: list[int]  # Номера шагов, от которых зависит
    estimated_time: str  # "1min", "5min", "10min"

class PlanningEngine:
    """Движок планирования."""
    
    def __init__(
        self,
        llm: LLMProvider,
        cross_file_analyzer: CrossFileAnalyzer,
    ):
        self.llm = llm
        self.cross_file_analyzer = cross_file_analyzer
    
    async def create_plan(
        self,
        task: str,
        project_context: str,
    ) -> Plan:
        """
        Создать план выполнения задачи.
        
        Pipeline:
        1. LLM анализирует задачу
        2. Определяет какие файлы нужно изменить
        3. Строит порядок шагов
        4. Оценивает усилия и риски
        """
        prompt = f"""
Analyze this task and create a detailed execution plan.

Task: {task}

Project context:
{project_context}

Return JSON:
{{
    "steps": [
        {{
            "order": 1,
            "description": "...",
            "files_to_modify": ["..."],
            "dependencies": [],
            "estimated_time": "..."
        }}
    ],
    "estimated_effort": "low|medium|high",
    "risks": ["..."]
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
        
        return self._parse_plan(response.text, task)
    
    def _parse_plan(self, text: str, task: str) -> Plan:
        """Парсить план из LLM ответа."""
        import json
        data = json.loads(text)
        
        steps = [
            PlanStep(
                order=step["order"],
                description=step["description"],
                files_to_modify=step["files_to_modify"],
                dependencies=step["dependencies"],
                estimated_time=step["estimated_time"]
            )
            for step in data["steps"]
        ]
        
        return Plan(
            task=task,
            steps=steps,
            estimated_effort=data.get("estimated_effort", "medium"),
            risks=data.get("risks", [])
        )
```

---

## ModificationPlanner

### Назначение

Планировщик изменений: определение конкретных изменений в файлах.

### Интерфейс

```python
@dataclass
class Modification:
    """Изменение в файле."""
    file_path: str
    change_type: Literal["add", "modify", "delete"]
    description: str
    code_snippet: str | None  # Код для добавления/замены
    line_range: tuple[int, int] | None  # Диапазон строк для замены

class ModificationPlanner:
    """Планировщик изменений."""
    
    def __init__(
        self,
        llm: LLMProvider,
        symbol_index: SymbolIndex,
    ):
        self.llm = llm
        self.symbol_index = symbol_index
    
    async def plan_modifications(
        self,
        plan_step: PlanStep,
        file_contents: dict[str, str],
    ) -> list[Modification]:
        """
        Запланировать изменения для шага плана.
        
        Args:
            plan_step: Шаг плана
            file_contents: Содержимое файлов
        
        Returns:
            Список изменений
        """
        prompt = f"""
Plan specific modifications for this step.

Step: {plan_step.description}

Files to modify: {', '.join(plan_step.files_to_modify)}

File contents:
{self._format_file_contents(file_contents)}

Return JSON:
{{
    "modifications": [
        {{
            "file_path": "...",
            "change_type": "add|modify|delete",
            "description": "...",
            "code_snippet": "...",
            "line_range": [start, end]
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
        
        return self._parse_modifications(response.text)
    
    def _parse_modifications(self, text: str) -> list[Modification]:
        """Парсить изменения из LLM ответа."""
        import json
        data = json.loads(text)
        
        return [
            Modification(
                file_path=mod["file_path"],
                change_type=mod["change_type"],
                description=mod["description"],
                code_snippet=mod.get("code_snippet"),
                line_range=tuple(mod["line_range"]) if mod.get("line_range") else None
            )
            for mod in data["modifications"]
        ]
```

---

## ChangeImpactAnalyzer

### Назначение

Анализ влияния изменений: какие файлы и символы будут затронуты.

### Интерфейс

```python
@dataclass
class ImpactAnalysis:
    """Анализ влияния изменений."""
    modified_files: list[str]
    affected_files: list[str]  # Файлы, которые могут быть затронуты
    affected_symbols: list[str]  # Символы, которые могут быть затронуты
    risk_level: Literal["low", "medium", "high"]
    recommendations: list[str]

class ChangeImpactAnalyzer:
    """Анализ влияния изменений."""
    
    def __init__(
        self,
        reference_index: ReferenceIndex,
        cross_file_analyzer: CrossFileAnalyzer,
    ):
        self.reference_index = reference_index
        self.cross_file_analyzer = cross_file_analyzer
    
    async def analyze_impact(
        self,
        modifications: list[Modification],
    ) -> ImpactAnalysis:
        """
        Анализировать влияние изменений.
        
        Pipeline:
        1. Для каждого изменённого файла найти символы
        2. Для каждого символа найти ссылки
        3. Определить затронутые файлы
        4. Оценить уровень риска
        """
        modified_files = list(set([mod.file_path for mod in modifications]))
        
        affected_files = set()
        affected_symbols = set()
        
        for file_path in modified_files:
            # Найти символы в файле
            symbols = self._find_symbols_in_file(file_path)
            
            for symbol in symbols:
                affected_symbols.add(symbol)
                
                # Найти ссылки на символ
                refs = self.reference_index.get_references(symbol)
                for ref in refs:
                    affected_files.add(ref.file_path)
        
        # Убрать сами изменённые файлы из affected
        affected_files -= set(modified_files)
        
        # Оценить риск
        risk_level = self._assess_risk(
            len(modified_files),
            len(affected_files),
            len(affected_symbols)
        )
        
        # Сформировать рекомендации
        recommendations = self._generate_recommendations(
            modified_files,
            list(affected_files),
            risk_level
        )
        
        return ImpactAnalysis(
            modified_files=modified_files,
            affected_files=list(affected_files),
            affected_symbols=list(affected_symbols),
            risk_level=risk_level,
            recommendations=recommendations
        )
    
    def _assess_risk(
        self,
        modified_count: int,
        affected_count: int,
        symbols_count: int,
    ) -> Literal["low", "medium", "high"]:
        """Оценить уровень риска."""
        total_impact = modified_count + affected_count + symbols_count
        
        if total_impact < 5:
            return "low"
        elif total_impact < 15:
            return "medium"
        else:
            return "high"
    
    def _generate_recommendations(
        self,
        modified_files: list[str],
        affected_files: list[str],
        risk_level: str,
    ) -> list[str]:
        """Сформировать рекомендации."""
        recommendations = []
        
        if risk_level == "high":
            recommendations.append("Consider breaking this change into smaller steps")
            recommendations.append("Run all tests after each modification")
        
        if affected_files:
            recommendations.append(f"Check these affected files: {', '.join(affected_files[:5])}")
        
        recommendations.append("Run linter to check for style issues")
        recommendations.append("Run tests to verify changes")
        
        return recommendations
```

---

## Интеграция с ExecutionEngine

```python
class ExecutionEngine:
    def __init__(
        self,
        planning_engine: PlanningEngine,
        modification_planner: ModificationPlanner,
        impact_analyzer: ChangeImpactAnalyzer,
        ...
    ):
        self.planning_engine = planning_engine
        self.modification_planner = modification_planner
        self.impact_analyzer = impact_analyzer
    
    async def execute_with_planning(self, session, task):
        # 1. Создать план
        plan = await self.planning_engine.create_plan(task, project_context)
        
        # 2. Для каждого шага плана
        for step in plan.steps:
            # 3. Запланировать изменения
            modifications = await self.modification_planner.plan_modifications(
                step, file_contents
            )
            
            # 4. Анализировать влияние
            impact = await self.impact_analyzer.analyze_impact(modifications)
            
            # 5. Показать пользователю
            await self._show_plan_to_user(step, impact)
            
            # 6. Выполнить изменения
            for mod in modifications:
                await self._apply_modification(mod)
            
            # 7. Проверить результаты
            await self._verify_changes(impact)
```

---

## Roadmap реализации

### Phase 4: Базовая реализация (3 недели)

**Задачи:**
- [ ] Реализовать `PlanningEngine` с созданием плана
- [ ] Реализовать `ModificationPlanner` с планированием изменений
- [ ] Unit tests

**Результат:** Базовое планирование изменений.

### Phase 4: Расширенная реализация (2 недели)

**Задачи:**
- [ ] Реализовать `ChangeImpactAnalyzer` с анализом влияния
- [ ] Реализовать оценку риска
- [ ] Интеграция с ExecutionEngine
- [ ] Integration tests

**Результат:** Полное планирование с анализом влияния.

---

## Дополнительные материалы

- [Context Manager Architecture](../context-manager/ARCHITECTURE.md) — детальная архитектура Context Manager
- [System Architecture](./SYSTEM_ARCHITECTURE.md) — общая архитектура системы
- [Code Understanding](./CODE_UNDERSTANDING.md) — понимание кодовой базы
