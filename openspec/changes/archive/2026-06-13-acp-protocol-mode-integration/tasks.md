## 1. Mode values и валидация
- [x] 1.1 Определить константы MODE_PLAN, MODE_STANDARD, MODE_BYPASS
- [x] 1.2 Создать валидатор mode в state.py
- [x] 1.3 Добавить backward compatibility mapping (ask→standard, code→bypass, architect→plan, debug→standard)
- [x] 1.4 Unit-тесты валидации mode

## 2. session/set_mode handler
- [x] 2.1 Обновить session_set_mode() в config.py — валидация modeId
- [x] 2.2 Отправка notification mode_changed при успешной смене
- [x] 2.3 Обработка невалидного modeId → ошибка -32602
- [x] 2.4 Unit-тесты session_set_mode (test_config_mode.py)

## 3. Mode в permission decision chain
- [x] 3.1 Обновить PermissionManager.decide() — mode check первым
- [x] 3.2 mode=plan → reject write/execute
- [x] 3.3 mode=bypass → allow все инструменты
- [x] 3.4 mode=standard → существующий policy chain
- [x] 3.5 Unit-тесты permission decision с mode (test_directives_mode.py, test_permission_manager.py)

## 4. Tool execution по mode
- [x] 4.1 Обновить directives.py — tool execution учитывает mode
- [x] 4.2 mode=plan: блокировать edit/delete/execute, разрешить read/search
- [x] 4.3 mode=standard: permission request (текущий ask flow)
- [x] 4.4 mode=bypass: auto-execute (текущий code flow)
- [x] 4.5 Integration тесты tool execution по mode (test_mode_integration.py)

## 5. Slash command /mode
- [x] 5.1 Обновить AVAILABLE_MODES → ["plan", "standard", "bypass"]
- [x] 5.2 Обновить описания режимов
- [x] 5.3 Обновить обработку аргументов
- [x] 5.4 Unit-тесты /mode command (test_mode_command.py)

## 6. Session setup — modes state
- [x] 6.1 Обновить build_modes_state() в session.py
- [x] 6.2 Возвращать availableModes: plan, standard, bypass
- [x] 6.3 currentModeId из session.config_values["mode"]
- [x] 6.4 Обновить _default_config_specs в core.py

## 7. Child session mode inheritance
> Перенесено в spec'и стратегий — child sessions создаются только в
> OrchestratedStrategy, HierarchicalStrategy, ChoreographyStrategy.
> Задачи будут реализованы вместе со стратегиями.

## 8. Backward compatibility
- [x] 8.1 Migration function: old_mode → new_mode (уже реализовано в mode.py)
- [x] 8.2 Deprecation warning при загрузке старого mode (уже реализовано в state.py)
- [x] 8.3 Обновить config option builder для mode (уже обновлено в core.py)
- [x] 8.4 Unit-тесты backward compatibility (test_mode_backward_compat.py)

## 9. Тесты
- [x] 9.1 Unit-тесты mode валидации (уже реализовано в test_mode.py)
- [x] 9.2 Unit-тесты session_set_mode (test_config_mode.py)
- [x] 9.3 Unit-тесты permission decision с mode (test_directives_mode.py, test_permission_manager.py)
- [x] 9.4 Unit-тесты tool execution по mode (test_directives_mode.py, test_mode_integration.py)
- [x] 9.5 Unit-тесты /mode command (test_mode_command.py)
- [x] 9.6 Unit-тесты modes state (test_session_modes.py)
- [ ] 9.7 Integration тесты mode inheritance (перенесено в spec'и стратегий)
- [x] 9.8 Integration тесты mode × strategy matrix (test_mode_strategy_matrix.py)
- [x] 9.9 Integration тесты backward compatibility (test_mode_backward_compat.py)

## 10. Верификация
- [x] 10.1 uv run ruff check . (lint проходит для новых тестов)
- [x] 10.2 uv run ty check (typecheck — pre-existing errors, не связаны с mode)
- [x] 10.3 uv run python -m pytest (137 mode-related tests passed)
- [ ] 10.4 make check (lint/typecheck — pre-existing errors)
