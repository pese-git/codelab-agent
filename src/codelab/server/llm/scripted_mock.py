"""Сценарный (scriptable) Mock LLM провайдер — конечный автомат для e2e.

Позволяет описать диалог с агентом как сценарий и детерминированно
прогонять полные flow взаимодействия клиента с агентом через транспорт
(включая tool calls, permission и client RPC — fs/terminal).

Сценарий — это список "ходов" (turns). Каждый ход матчится по последнему
сообщению пользователя (подстрока) и задаёт последовательность ответов
модели (replies). Первый reply возвращается на пользовательский промпт,
последующие — по мере поступления tool-результатов. Reply с tool_calls
завершается StopReason.TOOL_USE, reply с текстом — END_TURN.

Формат сценария (JSON):
    {
      "turns": [
        {"when_user": ["привет"], "replies": [{"text": "Привет!"}]},
        {"when_user": ["README", "прочти"], "replies": [
            {"tool_calls": [
                {"name": "fs_read_text_file", "arguments": {"path": "README.md"}}
            ]},
            {"text": "Готово, прочитал файл."}
        ]}
      ],
      "default": {"text": "Не понял запрос."}
    }

Подстановки в arguments (резолвятся из последнего tool-результата):
    "${terminal_id}" → terminalId из предыдущего tool-результата.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from codelab.server.llm.base import LLMCapabilities, LLMConfig, LLMProvider
from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    LLMMessage,
    LLMToolCall,
    StopReason,
)

logger = structlog.get_logger()

_TERMINAL_ID_RE = re.compile(r'"?terminal[_ ]?id"?\s*[:=]\s*"?([\w-]+)"?', re.IGNORECASE)


@dataclass
class ScriptedReply:
    """Один ответ модели в рамках хода сценария."""

    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ScriptedTurn:
    """Ход сценария: триггер по сообщению пользователя + последовательность ответов."""

    when_user: list[str]
    replies: list[ScriptedReply]


class ScriptedMockLLMProvider(LLMProvider):
    """Mock-провайдер, проигрывающий сценарий как конечный автомат.

    Состояние: активный ход и индекс следующего reply. Ход выбирается по
    последнему сообщению пользователя; внутри хода replies проигрываются
    последовательно по мере прихода tool-результатов.
    """

    def __init__(
        self,
        turns: list[ScriptedTurn] | None = None,
        default_reply: ScriptedReply | None = None,
    ) -> None:
        self._turns = turns or []
        self._default_reply = default_reply or ScriptedReply(text="Mock response")
        self._config: LLMConfig | None = None
        self.last_request: CompletionRequest | None = None

        # Состояние автомата
        self._active_turn: ScriptedTurn | None = None
        self._reply_index: int = 0
        self._call_counter: int = 0

    # ------------------------------------------------------------------ #
    # Фабрики
    # ------------------------------------------------------------------ #

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScriptedMockLLMProvider:
        """Построить провайдер из dict-сценария."""
        turns: list[ScriptedTurn] = []
        for turn in data.get("turns", []):
            when = turn.get("when_user", [])
            if isinstance(when, str):
                when = [when]
            replies = [
                ScriptedReply(
                    text=r.get("text", ""),
                    tool_calls=r.get("tool_calls", []),
                )
                for r in turn.get("replies", [])
            ]
            turns.append(ScriptedTurn(when_user=list(when), replies=replies))

        default_data = data.get("default")
        default_reply = (
            ScriptedReply(
                text=default_data.get("text", "Mock response"),
                tool_calls=default_data.get("tool_calls", []),
            )
            if isinstance(default_data, dict)
            else None
        )
        return cls(turns=turns, default_reply=default_reply)

    @classmethod
    def from_file(cls, path: str | Path) -> ScriptedMockLLMProvider:
        """Загрузить сценарий из JSON-файла."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # ------------------------------------------------------------------ #
    # LLMProvider интерфейс
    # ------------------------------------------------------------------ #

    @property
    def name(self) -> str:
        return "mock"

    @property
    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_function_calling=True,
        )

    async def initialize(self, config: LLMConfig) -> None:
        self._config = config
        logger.debug("scripted mock llm provider initialized")

    async def create_completion(
        self, request: CompletionRequest
    ) -> CompletionResponse:
        self.last_request = request
        reply = self._next_reply(request.messages)
        return self._to_response(reply, request)

    async def stream_completion(
        self, request: CompletionRequest
    ) -> AsyncGenerator[CompletionResponse, None]:
        self.last_request = request
        reply = self._next_reply(request.messages)
        yield self._to_response(reply, request)

    # ------------------------------------------------------------------ #
    # Логика автомата
    # ------------------------------------------------------------------ #

    def _next_reply(self, messages: list[LLMMessage]) -> ScriptedReply:
        """Выбрать следующий reply по состоянию диалога."""
        last = messages[-1] if messages else None
        last_is_tool_result = last is not None and last.role == "tool"

        # Продолжение активного хода после tool-результата
        if last_is_tool_result and self._active_turn is not None:
            if self._reply_index < len(self._active_turn.replies):
                reply = self._active_turn.replies[self._reply_index]
                self._reply_index += 1
                self._maybe_finish(reply)
                return reply
            # Реплики закончились — завершаем ход
            self._active_turn = None
            return self._default_reply

        # Новый ход: матчим по последнему сообщению пользователя
        user_text = self._last_user_text(messages)
        turn = self._match_turn(user_text)
        if turn is None or not turn.replies:
            self._active_turn = None
            return self._default_reply

        self._active_turn = turn
        self._reply_index = 1
        reply = turn.replies[0]
        self._maybe_finish(reply)
        return reply

    def _maybe_finish(self, reply: ScriptedReply) -> None:
        """Сбросить активный ход, если reply финальный (без tool_calls)."""
        if not reply.tool_calls:
            self._active_turn = None
            self._reply_index = 0

    @staticmethod
    def _last_user_text(messages: list[LLMMessage]) -> str:
        for msg in reversed(messages):
            if msg.role == "user":
                content = msg.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    # Мультимодальный контент: собираем текстовые части
                    parts = [
                        getattr(p, "text", "") for p in content if hasattr(p, "text")
                    ]
                    return " ".join(parts)
                return ""
        return ""

    def _match_turn(self, user_text: str) -> ScriptedTurn | None:
        text_lower = user_text.lower()
        for turn in self._turns:
            for trigger in turn.when_user:
                if trigger.lower() in text_lower:
                    return turn
        return None

    def _to_response(
        self, reply: ScriptedReply, request: CompletionRequest
    ) -> CompletionResponse:
        tool_calls: list[LLMToolCall] = []
        for tc in reply.tool_calls:
            self._call_counter += 1
            arguments = self._resolve_placeholders(
                tc.get("arguments", {}), request.messages
            )
            tool_calls.append(
                LLMToolCall(
                    id=tc.get("id") or f"call_{self._call_counter}",
                    name=tc["name"],
                    arguments=arguments,
                )
            )

        return CompletionResponse(
            text=reply.text,
            tool_calls=tool_calls,
            stop_reason=StopReason.TOOL_USE if tool_calls else StopReason.END_TURN,
            model=request.model,
        )

    def _resolve_placeholders(
        self, arguments: dict[str, Any], messages: list[LLMMessage]
    ) -> dict[str, Any]:
        """Подставить ${terminal_id} из последнего tool-результата."""
        if not any(v == "${terminal_id}" for v in arguments.values()):
            return dict(arguments)

        terminal_id = self._last_terminal_id(messages)
        resolved: dict[str, Any] = {}
        for key, value in arguments.items():
            if value == "${terminal_id}" and terminal_id is not None:
                resolved[key] = terminal_id
            else:
                resolved[key] = value
        return resolved

    @staticmethod
    def _last_terminal_id(messages: list[LLMMessage]) -> str | None:
        for msg in reversed(messages):
            if msg.role != "tool":
                continue
            content = msg.content if isinstance(msg.content, str) else ""
            match = _TERMINAL_ID_RE.search(content)
            if match:
                return match.group(1)
        return None
