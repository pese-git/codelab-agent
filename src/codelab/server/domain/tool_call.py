"""Domain model для ToolCall и ToolResult."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .value_objects import TERMINAL_TOOL_CALL_STATUSES, FileLocation, ToolCallStatus


def answer_tool_call_id(tool_call_id_from_llm: str | None, tool_call_id: str) -> str:
    """Идентификатор, которым вызов адресуется **модели** (`role: tool`).

    Единственный владелец правила перевода «внутренняя идентичность → идентичность
    для модели» (шаг 1 ADR-008). Раньше правило было продублировано десятью
    выражениями `tool_call_id_from_llm or tool_call_id` в четырёх модулях.

    Внутренний `tool_call_id` (`call_NNN`) выдаёт агрегат и им ключуются состояние
    и ACP-нотификации. Модель адресует свой вызов собственным идентификатором,
    поэтому ответ обязан идти под ним. Fallback на внутренний — не подстраховка, а
    рабочая ветка: у путей без LLM (client-RPC, отмена, служебные вызовы)
    идентификатора модели не существует, и ответ всё равно обязан быть отправлен,
    иначе вызов остаётся без `role: tool` и следующий запрос нарушает контракт
    LLM-API (P2-38).
    """
    return tool_call_id_from_llm or tool_call_id


@dataclass(frozen=True)
class ToolResult:
    """Domain model для результата выполнения tool call."""

    locations: list[FileLocation] = field(default_factory=list)
    raw_output: dict[str, Any] = field(default_factory=dict)
    # `content` — payload `tool_call_update`, отправленного клиенту (write-фаза D4-b/b3, ADR-006).
    # Парное поле `result_content` удалено в ADR-007 (шаг B1): его писал только turn-путь и не
    # читал никто — 21% документа сессии уходил на диск без потребителя.
    content: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolCall:
    """Domain entity — внутреннее представление tool call.

    НЕ является ACP Protocol Model. Для wire format использовать ToolCallState.
    Конвертация через ToolCallMapper.

    Мутабельна намеренно: это entity с идентичностью (`id`) и жизненным циклом
    статуса, а не value object. `frozen=True` заставлял пересобирать объект на
    каждую смену статуса, из-за чего `ToolCallRegistry.update` терял поля, не
    перечисленные в пересборке (write-фаза, фаза B ADR-006).
    """

    id: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    status: ToolCallStatus = ToolCallStatus.PENDING
    result: ToolResult | None = None
    locations: list[FileLocation] = field(default_factory=list)
    raw_output: dict[str, Any] = field(default_factory=dict)
    # Состояние сессии, переехавшее из wire-DTO по семантике (write-фаза D4-b/b3, ADR-006):
    # `kind` — ACP-вид, ключ permission-политики; `title` — display, персистится для replay;
    # `tool_call_id_from_llm` — опаковый корреляционный id для связки с историей.
    kind: str = "other"
    title: str | None = None
    tool_call_id_from_llm: str | None = None

    @property
    def answer_id(self) -> str:
        """Идентификатор, которым этот вызов адресуется модели.

        Делегирует `answer_tool_call_id`: правило одно, точек входа две — для
        вызывающих с объектом на руках и для тех, у кого есть только пара
        идентификаторов.
        """
        return answer_tool_call_id(self.tool_call_id_from_llm, self.id)

    @property
    def is_terminal(self) -> bool:
        """Статус финальный — дальнейших переходов нет.

        Производное от матрицы переходов, а не отдельный список: раньше набор был
        продублирован и мог разойтись с ней.
        """
        return self.status in TERMINAL_TOOL_CALL_STATUSES

    @property
    def is_in_flight(self) -> bool:
        """Вызов исполняется прямо сейчас — ответ модели произведёт исполнитель.

        Отвечает на вопрос владения: `role: tool` принадлежит тому, кто вызов
        исполняет, пока он жив. «Не начинался» (`pending`) и «в полёте»
        (`in_progress`) требуют разных действий при отмене, а предикат «статус не
        финальный» их смешивал — и вызов получал два ответа на один
        `answer_id` (P2-63, измерено живьём 2026-08-10).

        Признак читает **статус**, а не журнал, и потому полон: `in_progress`
        выставляется перед каждым исполнением. Событие журнала при этом пишет
        только путь без разрешения (`tool_processor.py:752`); resume после
        разрешения (`:924`) меняет статус молча. Отсюда наблюдение прогона
        2026-08-10 — `in_progress` в журнале лишь у `terminal/wait_for_exit`
        (3 из 3) — которое описывает видимость события, а не полноту признака.

        Гарантией он тем не менее не является: между созданием вызова и
        выставлением статуса есть окно. Гарантию несёт идемпотентность
        `Session.add_tool_result`, а этот предикат выбирает, **чей текст**
        достанется модели.
        """
        return self.status == ToolCallStatus.IN_PROGRESS
