"""ConversationSummarizer — LLM-суммаризация диалога.

Слой B — Жизненный цикл (Phase 3).

Сохраняет ключевые решения и состояние задачи при сжатии контекста.
При недоступности LLM деградирует до усечения сырого результата.
"""

from __future__ import annotations

import structlog

from codelab.server.agent.context.budget import DefaultTokenBudgetManager
from codelab.server.agent.context.interfaces import (
    ConversationSummarizer,
    TokenCounter,
)
from codelab.server.llm.base import LLMProvider
from codelab.server.llm.models import CompletionRequest, LLMMessage

logger = structlog.get_logger(__name__)

SUMMARIZATION_PROMPT = """Summarize the following conversation concisely.

Preserve:
1. Key decisions made and their rationale
2. Current task state and progress
3. Important file paths and code references mentioned
4. Unresolved issues or open questions
5. Critical context needed to continue the work

Target length: approximately {target_tokens} tokens.

Conversation:
{conversation_text}

Provide a clear, structured summary:"""


class LLMConversationSummarizer(ConversationSummarizer):
    """Суммаризатор диалога на основе LLM.

    При недоступности LLM деградирует до усечения сырого результата
    через TokenBudgetManager.bound_content().
    """

    def __init__(
        self,
        llm: LLMProvider | None = None,
        model: str = "openai/gpt-4o-mini",
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._llm = llm
        self._model = model
        self._token_counter = token_counter
        self._budget_manager = DefaultTokenBudgetManager()

    async def summarize(
        self,
        messages: list[LLMMessage],
        *,
        target_tokens: int,
    ) -> LLMMessage:
        """Суммаризовать диалог, сохранив ключевые решения.

        Args:
            messages: Сообщения для суммаризации
            target_tokens: Целевой размер summary в токенах

        Returns:
            LLMMessage с суммаризированным содержанием
        """
        if not messages:
            logger.warning("conversation_summarizer_empty_messages")
            return LLMMessage(role="assistant", content="[Empty conversation]")

        conversation_text = self._format_conversation(messages)

        if self._llm is None:
            logger.warning(
                "conversation_summarizer_no_llm_degrading",
                message_count=len(messages),
                target_tokens=target_tokens,
            )
            return self._fallback_truncate(conversation_text, target_tokens)

        try:
            summary = await self._llm_summarize(conversation_text, target_tokens)
            if not summary or not summary.strip():
                logger.warning(
                    "conversation_summarizer_empty_result_degrading",
                    message_count=len(messages),
                )
                return self._fallback_truncate(conversation_text, target_tokens)

            logger.info(
                "conversation_summarizer_success",
                message_count=len(messages),
                summary_length=len(summary),
                target_tokens=target_tokens,
            )

            return LLMMessage(
                role="assistant",
                content=f"[Summary of {len(messages)} messages]\n{summary}",
            )

        except Exception:
            logger.exception(
                "conversation_summarizer_failed_degrading",
                message_count=len(messages),
            )
            return self._fallback_truncate(conversation_text, target_tokens)

    async def _llm_summarize(
        self,
        conversation_text: str,
        target_tokens: int,
    ) -> str:
        """Вызвать LLM для суммаризации."""
        prompt = SUMMARIZATION_PROMPT.format(
            target_tokens=target_tokens,
            conversation_text=conversation_text,
        )

        request = CompletionRequest(
            model=self._model,
            messages=[LLMMessage(role="user", content=prompt)],
            max_tokens=target_tokens * 2,
            temperature=0.0,
        )

        response = await self._llm.create_completion(request)
        return response.text

    def _fallback_truncate(
        self,
        text: str,
        target_tokens: int,
    ) -> LLMMessage:
        """Усечь сырой результат через bound_content."""
        truncated = self._budget_manager.bound_content(text, target_tokens)
        return LLMMessage(
            role="assistant",
            content=f"[Truncated summary]\n{truncated}",
        )

    @staticmethod
    def _format_conversation(messages: list[LLMMessage]) -> str:
        """Форматировать сообщения в текст для суммаризации."""
        parts: list[str] = []
        for msg in messages:
            role = msg.role
            content = msg.content if isinstance(msg.content, str) else str(msg.content or "")
            if content:
                parts.append(f"[{role}] {content}")
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    parts.append(f"[{role}:tool_call] {tc.name}({tc.arguments})")
        return "\n".join(parts)
