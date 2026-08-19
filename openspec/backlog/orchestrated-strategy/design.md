## Decision 1: Structured Outputs для RouteDecision

**Контекст:** Orchestrator должен принимать решения о маршрутизации субагентов.

**Решение:** Использовать Pydantic model с LLM Structured Outputs — гарантирует валидный JSON, не нужно парсить вручную.

**Tradeoffs:**
- ✅ Валидный JSON всегда
- ✅ Pydantic автоматически проверяет схему
- ⚠️ Зависит от поддержки Structured Outputs провайдером (OpenAI, Anthropic поддерживают)

## Decision 2: TokenSlicer — отдельный компонент

**Контекст:** Ответы субагентов нужно суммаризировать перед добавлением в контекст координатора.

**Решение:** Отдельный класс TokenSlicer с дешёвой моделью для суммаризации.

**Tradeoffs:**
- ✅ Дешевле чем использовать основную модель
- ✅ Skip threshold экономит токены на маленьких ответах
- ⚠️ Дополнительный LLM call на каждом шаге

## Decision 3: SubAgentCoordinator вместо HybridContextManager

**Контекст:** Управление контекстом в мультиагентных стратегиях включает TokenSlicer, ContextCompactor и Child Sessions.

**Решение:** `HybridContextManager` упразднён. Его ответственности разделены:
- **Context management** → `FederatedContextManager` (FCM): хранение скоупов, шеринг, compaction через `DefaultContextCompactor`
- **Sub-agent lifecycle** → `SubAgentCoordinator`: только TokenSlicer + child session creation

```python
class SubAgentCoordinator:
    _slicer: TokenSlicer      # суммаризация ответов субагентов
    _storage: SessionStorage  # создание и связывание child sessions
    # ContextCompactor УДАЛЁН — FCM.optimize_and_build_payload() покрывает
```

**Tradeoffs:**
- ✅ Нет дублирования: FCM уже содержит DefaultContextCompactor
- ✅ Чистое разделение: FCM = "что хранить", SubAgentCoordinator = "как вызвать и записать"
- ✅ Стратегии явно управляют контекстом через FCM API
- ⚠️ Стратегии зависят от FCM напрямую (не через посредника)

## Decision 4: max_steps = 7 по умолчанию

**Контекст:** Нужен предохранитель от бесконечных циклов маршрутизации.

**Решение:** max_steps = 7 (как в OpenCode), настраивается через codelab.toml.

**Tradeoffs:**
- ✅ 7 шагов достаточно для большинства задач
- ⚠️ Может быть недостаточно для очень сложных задач
