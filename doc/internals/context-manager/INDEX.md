# Context Manager — Индекс документации (канон)

> **Статус:** Канон — отражает [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md).
> Заменяет дизайн-документы `doc/internals/architecture/fcm/` (архивируются на Phase 0).

Единый source-of-truth по менеджеру контекста CodeLab — консолидация двух дизайнов
(CM «что читать и как обновлять» + FCM «как хранить дёшево») в единую архитектуру.

## Документы

| Документ | Назначение | Для кого |
|----------|------------|----------|
| [CONSOLIDATED_ARCHITECTURE.md](./CONSOLIDATED_ARCHITECTURE.md) | Полная архитектура: слои A–D, путь payload, жизненный цикл, кэш, сжатие, мультиагент, флаги, фазы 0–6 | Все |
| [INTERFACES.md](./INTERFACES.md) | Замороженные ABC/контракты (Phase 0) | Разработчики |
| [DATA_MODELS.md](./DATA_MODELS.md) | Структуры данных (dataclass), `PayloadEnvelope`, конфиг | Разработчики |
| [PHASE_0_SPEC.md](./PHASE_0_SPEC.md) … [PHASE_6_SPEC.md](./PHASE_6_SPEC.md) | Детальные спеки фаз — задачи, acceptance, DoD, риски | Разработчики |
| [STRATEGY_INTEGRATION.md](./STRATEGY_INTEGRATION.md) | План интеграции 4 стратегий (Single/Orchestrated/Choreography/Hierarchical) с ContextManager | Разработчики |
| [WALKTHROUGH_EXAMPLE.md](./WALKTHROUGH_EXAMPLE.md) | Сквозной пример: вход → преобразования → выход на нескольких итерациях agent loop | Все |
| [ADR-002](../architecture/adr/ADR-002-context-manager-consolidation.md) | Все архитектурные решения и обоснования | Архитекторы, reviewers |

## Статус готовности к разработке

| Фаза | Спецификация | Статус |
|------|--------------|--------|
| Phase 0 — Каркас + контракты | [PHASE_0_SPEC.md](./PHASE_0_SPEC.md) + INTERFACES + DATA_MODELS | ✅ Готово к разработке |
| Phase 1 — MVP-сбор | [PHASE_1_SPEC.md](./PHASE_1_SPEC.md) | ✅ Готово к разработке |
| Phase 2 — Слой хранения C | [PHASE_2_SPEC.md](./PHASE_2_SPEC.md) | ✅ Готово к разработке |
| Phase 3 — Источники + сжатие | [PHASE_3_SPEC.md](./PHASE_3_SPEC.md) | ✅ Готово к разработке |
| Phase 4 — Инкрементальность | [PHASE_4_SPEC.md](./PHASE_4_SPEC.md) | ✅ Готово к разработке |
| Phase 5 — Полный DependencyGraph | [PHASE_5_SPEC.md](./PHASE_5_SPEC.md) | ✅ Готово к разработке |
| Phase 6 — Мультиагент | [PHASE_6_SPEC.md](./PHASE_6_SPEC.md) | ✅ Готово к разработке |

> Все фазы 0–6 специфицированы (задачи, acceptance, DoD, риски). Архитектура
> и контракты зафиксированы в CONSOLIDATED_ARCHITECTURE / INTERFACES / DATA_MODELS.

## Ключевые решения (из ADR-002)

- **База** — CM; FCM вливается слоем C (хранение/эффективность).
- **Жизненный цикл** — инкрементальная модель (`baseline/tail` с Phase 0; `Epoch` с Phase 4). Обоснование — длинные сессии.
- **Кэширование** — два комплементарных кэша; единый сигнал инвалидации файла.
- **Мультиагент** — изоляция по умолчанию; федерация — кандидат на отказ.
- **Флаги** — `agents.context.*` (замена `enable_fcm`).
- **Канон** — `doc/internals/context-manager/`; `fcm/` → архив.
