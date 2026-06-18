"""Executor для инструмента update_plan.

Обрабатывает вызов update_plan и обновляет план в состоянии сессии.
Результат выполнения возвращается как подтверждение обновления.
"""

from __future__ import annotations

from typing import Any

import structlog

from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.base import ToolExecutor

logger = structlog.get_logger()

# Допустимые значения для валидации
ALLOWED_PRIORITIES = frozenset({"low", "medium", "high"})
ALLOWED_STATUSES = frozenset({"pending", "in_progress", "completed", "cancelled"})


class PlanToolExecutor(ToolExecutor):
    """Executor для инструмента update_plan.
    
    Обрабатывает вызов update_plan и обновляет план в состоянии сессии.
    Не требует ClientRPC или разрешений пользователя.
    """

    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить update_plan - обновить план в состоянии сессии.
        
        Args:
            session: Состояние сессии
            arguments: Словарь с ключом 'entries' (список шагов плана)
            
        Returns:
            ToolExecutionResult с подтверждением обновления
        """
        raw_entries = arguments.get("entries", [])
        
        if not isinstance(raw_entries, list):
            return ToolExecutionResult(
                success=False,
                error="entries must be a list",
            )
        
        # Валидация и нормализация entries
        validated_entries = self._validate_entries(raw_entries)
        
        if not validated_entries:
            return ToolExecutionResult(
                success=False,
                error="No valid plan entries provided",
            )
        
        # Обновить план в состоянии сессии
        # ВАЖНО: Фактическое обновление и отправка notification
        # происходит в PromptOrchestrator через PlanBuilder
        # Здесь мы просто подтверждаем успешную валидацию
        
        logger.debug(
            "update_plan tool executed",
            session_id=session.session_id,
            num_entries=len(validated_entries),
        )
        
        # Возвращаем результат с информацией о плане
        return ToolExecutionResult(
            success=True,
            output=f"Plan updated with {len(validated_entries)} entries",
            metadata={
                "entries_count": len(validated_entries),
                "validated_entries": validated_entries,
            },
        )
    
    def _validate_entries(
        self,
        raw_entries: list[Any],
    ) -> list[dict[str, str]]:
        """Валидировать и нормализовать entries.
        
        Args:
            raw_entries: Сырые entries из arguments
            
        Returns:
            Список валидных entries с нормализованными полями
        """
        valid_entries: list[dict[str, str]] = []
        
        for raw in raw_entries:
            if not isinstance(raw, dict):
                continue
            
            # Требуем content
            content = raw.get("content") or raw.get("title")
            if not isinstance(content, str) or not content.strip():
                logger.debug(
                    "plan entry skipped: missing content",
                    raw=raw,
                )
                continue
            
            # Нормализуем priority
            raw_priority = raw.get("priority", "medium")
            priority = raw_priority if raw_priority in ALLOWED_PRIORITIES else "medium"
            
            # Нормализуем status
            raw_status = raw.get("status", "pending")
            status = raw_status if raw_status in ALLOWED_STATUSES else "pending"
            
            # Опциональное description
            description = raw.get("description", "")
            if not isinstance(description, str):
                description = ""
            
            valid_entries.append({
                "content": content.strip(),
                "priority": priority,
                "status": status,
                "description": description.strip(),
            })
        
        return valid_entries
