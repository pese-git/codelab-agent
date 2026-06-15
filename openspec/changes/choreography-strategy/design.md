## Decision 1: Child session только для winner

**Контекст:** ChoreographyStrategy вызывает N агентов параллельно.

**Решение:** Child session создаётся только для winner-агента после Conflict Resolution. Это минимизирует overhead (1 child session вместо N) и сохраняет навигацию к деталям выполненной работы.

**Tradeoffs:**
- ✅ Экономия storage и памяти
- ✅ Навигация к winner деталям
- ⚠️ Ответы проигравших не сохраняются в child sessions (только в EventTimeline)

## Decision 2: Conflict Resolution через Priority Queue

**Контекст:** Несколько агентов могут вернуть action_taken=True.

**Решение:** Winner = агент с наименьшим priority из agent config. При равном priority — первый по порядку.

**Tradeoffs:**
- ✅ Простая и предсказуемая логика
- ✅ Настраивается через agent config
- ⚠️ Не учитывает качество ответа, только priority

## Decision 3: asyncio.gather с return_exceptions=True

**Контекст:** При cancellation нужно отменить все параллельные calls.

**Решение:** asyncio.gather(*tasks, return_exceptions=True) — все параллельные calls, CancelledError обрабатывается как результат. Conflict Resolution полностью пропускается при cancellation.

**Tradeoffs:**
- ✅ Все tasks отменяются параллельно
- ✅ Частичные результаты игнорируются
- ⚠️ Нельзя отменить отдельные tasks
