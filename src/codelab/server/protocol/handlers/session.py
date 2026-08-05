"""Обработчики методов управления сессиями.

Содержит логику обработки session/new, session/load, session/list.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, cast

import structlog

from codelab.server.storage.document import ClientRuntimeCapabilities

from ...domain.session import Session as DomainSession
from ...domain.value_objects import ToolCallStatus
from ...messages import ACPMessage, JsonRpcId
from ...storage import SessionRepository
from ..session_factory import SessionFactory
from ..state import ProtocolOutcome
from .event_history_writer import EventHistoryWriter
from .session_replayer import SessionReplayer

# Используем structlog для структурированного логирования
logger = structlog.get_logger()


def _serialize_available_commands(
    commands: list,
) -> list[dict[str, Any]]:
    """Сериализует список available_commands для JSON.

    Преобразует Pydantic модели в dict для JSON сериализации.
    """
    result: list[dict[str, Any]] = []
    for cmd in commands:
        if isinstance(cmd, dict):
            result.append(cmd)
        elif hasattr(cmd, "model_dump"):
            result.append(cmd.model_dump(exclude_none=False))
        else:
            result.append(cmd)
    return result


def _cleanup_session_state(session: DomainSession) -> None:
    """Очищает незавершенные операции при переключении сессии.

    Выполняет следующие действия для безопасного переключения:
    1. Отменяет active turn, если он активен
    2. Отмечает все pending tool calls как cancelled и пишет это в events_history
    3. Добавляет permission request IDs в cancelled_permission_requests
    4. Добавляет RPC request IDs в cancelled_client_rpc_requests

    Отмена вызовов записывается в историю, потому что вызывается ДО
    `replay_history`: реплей подхватывает событие сам и клиент получает
    cancelled вместо pending. Без записи расходились три стороны — реплей
    (pending), состояние в памяти (cancelled) и диск (pending).

    Аргументы:
        session: Доменный агрегат сессии для очистки.

    Пример использования:
        _cleanup_session_state(session)
    """
    # Завершить active turn
    if session.active_turn is not None:
        session.active_turn.cancel_requested = True
        session.active_turn.phase = "cancelled"

        # Если был permission request, отменить его
        if session.active_turn.permission_request_id is not None:
            session.cancel_permission_request(session.active_turn.permission_request_id)

        # Если был pending client request, отменить его
        if session.active_turn.pending_external_request is not None:
            session.cancel_client_rpc_request(
                session.active_turn.pending_external_request.request_id
            )

        # Отложенный хвост батча (P2-40) не выполнится после переключения сессии.
        # Обязательно до очистки: `pending_batch` живёт в `active_turn`.
        session.answer_deferred_batch(reason="сессия была переключена")

        session.clear_active_turn()

    # Отметить все pending tool calls как cancelled
    history_writer = EventHistoryWriter()
    for tool_call in session.tool_calls.get_all():
        if tool_call.status == ToolCallStatus.PENDING:
            tool_call_id = tool_call.id
            session.tool_calls.update_status(tool_call_id, ToolCallStatus.CANCELLED)
            history_writer.save_tool_call_update(
                session,
                tool_call_id=tool_call_id,
                status="cancelled",
            )
            # Ответ модели на отменённый вызов: без него он остаётся без `role: tool`
            # и при следующем запросе история нарушает контракт LLM-API
            # (tech-debt P2-38, источник 2).
            session.add_tool_result(
                tool_call.tool_call_id_from_llm or tool_call_id,
                "Вызов не выполнялся: сессия была переключена. "
                "Запроси его снова, если он всё ещё нужен.",
            )


def session_new(
    request_id: JsonRpcId | None,
    params: dict[str, Any],
    require_auth: bool,
    authenticated: bool,
    config_specs: dict[str, dict[str, Any]],
    auth_methods: list[dict[str, Any]],
    runtime_capabilities: ClientRuntimeCapabilities | None,
    command_registry: Any | None = None,
) -> ACPMessage:
    """Создает новую in-memory сессию и возвращает ее идентификатор.

    Метод валидирует `cwd`, инициализирует config options и дефолтные
    slash-команды.

    Пример использования:
        response = session_new(
            "req_1", {"cwd": "/tmp", "mcpServers": []}, False, True, {}, [], None
        )
    """

    if require_auth and not authenticated:
        return ACPMessage.error_response(
            request_id,
            code=-32010,
            message="auth_required",
            data={"authMethods": auth_methods},
        )

    # По спецификации cwd должен быть абсолютным путем.
    cwd = params.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return ACPMessage.error_response(
            request_id,
            code=-32602,
            message="Invalid params: cwd must be an absolute path",
        )

    mcp_servers = params.get("mcpServers", [])
    if not isinstance(mcp_servers, list):
        return ACPMessage.error_response(
            request_id,
            code=-32602,
            message="Invalid params: mcpServers must be an array",
        )

    # Создаем сессию через фабрику
    config_values = {config_id: str(spec["default"]) for config_id, spec in config_specs.items()}

    # Динамическая генерация available_commands из CommandRegistry
    available_commands = (
        command_registry.get_commands_as_dicts() if command_registry is not None else []
    )

    session_state = SessionFactory.create_session(
        cwd=cwd,
        mcp_servers=mcp_servers,
        config_values=config_values,
        available_commands=available_commands,
        runtime_capabilities=runtime_capabilities,
    )

    return ACPMessage.response(
        request_id,
        {
            "sessionId": session_state.session_id,
            "configOptions": build_config_options(config_values, config_specs),
            "modes": build_modes_state(config_values, config_specs),
        },
    )


def _validate_session_load_params(
    request_id: JsonRpcId | None,
    session_id: Any,
    cwd: Any,
    mcp_servers: Any,
) -> ACPMessage | None:
    """Валидирует sessionId/cwd/mcpServers для session/load.

    Возвращает готовый error-response при ошибке, иначе `None`.
    """
    if not isinstance(session_id, str):
        return ACPMessage.error_response(
            request_id, code=-32602, message="Invalid params: sessionId is required"
        )
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return ACPMessage.error_response(
            request_id, code=-32602, message="Invalid params: cwd must be an absolute path"
        )
    if not isinstance(mcp_servers, list):
        return ACPMessage.error_response(
            request_id, code=-32602, message="Invalid params: mcpServers must be an array"
        )
    return None


def _replay_tool_calls_fallback(session: DomainSession, session_id: str) -> list[ACPMessage]:
    """Реплей tool call'ов из состояния, если их нет в `events_history`.

    Обратная совместимость с сессиями, созданными до сохранения `tool_call` событий
    в `events_history`.

    ВНИМАНИЕ (P2-42, пункт «честный реплей»): каждый вызов реплеится со статусом
    `pending` независимо от реального, а фактический статус досылается отдельным
    `tool_call_update`. Это второй источник расхождения wire↔состояние; выправляется
    отдельным шагом, здесь поведение сохранено как было.
    """
    has_tool_call_events = any(
        event.get("type") == "session_update"
        and event.get("update", {}).get("sessionUpdate") == "tool_call"
        for event in session.runtime.events_history
    )
    if has_tool_call_events or not session.tool_calls.get_all():
        return []

    notifications: list[ACPMessage] = []
    for tool_call in session.tool_calls.get_all():
        notifications.append(
            ACPMessage.notification(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "tool_call",
                        "toolCallId": tool_call.id,
                        "title": tool_call.title,
                        "kind": tool_call.kind,
                        "status": "pending",
                    },
                },
            )
        )
        if tool_call.status == ToolCallStatus.PENDING:
            continue
        update_payload: dict[str, Any] = {
            "sessionUpdate": "tool_call_update",
            "toolCallId": tool_call.id,
            "status": tool_call.status.value,
        }
        if tool_call.result and tool_call.result.content:
            update_payload["content"] = tool_call.result.content
        notifications.append(
            ACPMessage.notification(
                "session/update",
                {"sessionId": session_id, "update": update_payload},
            )
        )
    return notifications


async def session_load(
    request_id: JsonRpcId | None,
    params: dict[str, Any],
    require_auth: bool,
    authenticated: bool,
    config_specs: dict[str, dict[str, Any]],
    auth_methods: list[dict[str, Any]],
    session: DomainSession | None = None,
) -> ProtocolOutcome:
    """Загружает существующую сессию и реплеит состояние через updates.

    Возвращает `result: null` и набор `session/update` уведомлений:
    история сообщений, config options, команды и session info.

    Пример использования:
        outcome = await session_load(
            "req_1",
            {"sessionId": "sess_1", "cwd": "/tmp", "mcpServers": []},
            False,
            True,
            {},
            [],
            storage,
        )
    """

    if require_auth and not authenticated:
        return ProtocolOutcome(
            response=ACPMessage.error_response(
                request_id,
                code=-32010,
                message="auth_required",
                data={"authMethods": auth_methods},
            )
        )

    # Загрузка поддерживает in-memory сессии и реплей накопленной истории в `session/update`.
    session_id = params.get("sessionId")
    cwd = params.get("cwd")
    mcp_servers = params.get("mcpServers")

    param_error = _validate_session_load_params(request_id, session_id, cwd, mcp_servers)
    if param_error is not None:
        return ProtocolOutcome(response=param_error)
    # Валидация выше гарантирует типы — сужаем для type-checker'а.
    session_id = cast(str, session_id)
    cwd = cast(str, cwd)
    mcp_servers = cast(list, mcp_servers)

    # Сессию передаёт вызывающий, уже загрузивший её (`SessionLoadCommandHandler`):
    # вторая загрузка давала бы вторую копию, и мутации первой терялись бы —
    # `JsonFileStorage` отдаёт новый объект на каждый `load_session` (P2-42).
    if session is None:
        logger.warning("session_load_not_found", session_id=session_id)
        return ProtocolOutcome(
            response=ACPMessage.error_response(
                request_id,
                code=-32001,
                message=f"Session not found: {session_id}",
            )
        )

    # Очистить незавершенные операции перед переключением контекста.
    # Это предотвращает race conditions и утечки памяти при переключении сессий.
    _cleanup_session_state(session)

    # При загрузке фиксируем актуальный контекст клиента.
    session.apply_client_context(
        cwd=cwd,
        mcp_servers=[server for server in mcp_servers if isinstance(server, dict)],
        runtime_capabilities=session.config.runtime_capabilities,
    )

    notifications: list[ACPMessage] = []

    # Используем SessionReplayer для воспроизведения истории session/update уведомлений
    # согласно спецификации ACP (protocol/03-Session Setup.md, раздел 132):
    # "The Agent MUST replay the entire conversation to the Client
    # in the form of session/update notifications"
    replayer = SessionReplayer()
    history_notifications = replayer.replay_history(session)
    notifications.extend(history_notifications)

    # Реплеим latest_plan если он есть и не был в events_history
    plan_notification = replayer.replay_latest_plan(session)
    if plan_notification:
        notifications.append(plan_notification)

    fallback_notifications = _replay_tool_calls_fallback(session, session_id)
    notifications.extend(fallback_notifications)

    notifications.append(
        ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "config_option_update",
                    "configOptions": build_config_options(
                        session.config.config_values, config_specs
                    ),
                },
            },
        )
    )
    notifications.append(
        ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "available_commands_update",
                    "availableCommands": _serialize_available_commands(session.available_commands),
                },
            },
        )
    )
    notifications.append(
        session_info_notification(
            session_id=session_id,
            title=session.title,
            updated_at=session.updated_at,
        )
    )

    # Единственная точка наблюдаемости session/load: состав реплея нужен, чтобы
    # подтверждать поведенческую нейтральность при смене источника сессии (ADR-006).
    logger.info(
        "session_loaded",
        session_id=session_id,
        notifications_total=len(notifications),
        history_notifications=len(history_notifications),
        plan_replayed=plan_notification is not None,
        tool_call_fallback_used=bool(fallback_notifications),
        events_history=len(session.runtime.events_history),
        tool_calls=len(session.tool_calls.get_all()),
    )

    return ProtocolOutcome(
        response=ACPMessage.response(
            request_id,
            {
                "configOptions": build_config_options(session.config.config_values, config_specs),
                "modes": build_modes_state(session.config.config_values, config_specs),
            },
        ),
        notifications=notifications,
    )


async def session_list(
    request_id: JsonRpcId | None,
    params: dict[str, Any],
    repository: SessionRepository,
    session_list_page_size: int = 50,
) -> ACPMessage:
    """Возвращает список сессий с опциональной фильтрацией по `cwd`.

    Пример использования:
        response = await session_list("req_1", {"cwd": "/tmp"}, repository)
    """

    # Поддерживаем фильтрацию сессий по cwd для клиентских списков.
    cwd_filter = params.get("cwd")
    cursor = params.get("cursor")
    if cwd_filter is not None and (
        not isinstance(cwd_filter, str) or not Path(cwd_filter).is_absolute()
    ):
        return ACPMessage.error_response(
            request_id,
            code=-32602,
            message="Invalid params: cwd must be an absolute path",
        )
    if cursor is not None and not isinstance(cursor, str):
        return ACPMessage.error_response(
            request_id,
            code=-32602,
            message="Invalid params: cursor must be a string",
        )

    start_index = 0
    if isinstance(cursor, str):
        decoded = decode_session_cursor(cursor)
        if decoded is None:
            return ACPMessage.error_response(
                request_id,
                code=-32602,
                message="Invalid params: cursor is invalid",
            )
        start_index = decoded

    # Загружаем сессии через storage с пагинацией
    sessions_list: list[dict[str, Any]] = []
    storage_cursor = None
    while True:
        # Порт отдаёт облегчённую wire-проекцию, а не агрегат (CQRS-lite, ADR-006):
        # `session/list` нужны только title/updated_at/cwd, восстанавливать поведение
        # агрегата для списка незачем.
        page, next_cursor = await repository.list_sessions(
            cwd=cwd_filter if isinstance(cwd_filter, str) else None,
            cursor=storage_cursor,
            limit=100,
        )
        for session in page:
            sessions_list.append(
                {
                    "sessionId": session.session_id,
                    "cwd": session.cwd,
                    "title": session.title,
                    "updatedAt": session.updated_at,
                    "_meta": {},
                }
            )
        if next_cursor is None:
            break
        storage_cursor = next_cursor

    sorted_sessions = sorted(
        sessions_list, key=lambda item: str(item.get("updatedAt") or ""), reverse=True
    )
    page_end = start_index + session_list_page_size
    page = sorted_sessions[start_index:page_end]
    next_cursor: str | None = None
    if page_end < len(sorted_sessions):
        next_cursor = encode_session_cursor(page_end)

    return ACPMessage.response(request_id, {"sessions": page, "nextCursor": next_cursor})


def encode_session_cursor(index: int) -> str:
    """Кодирует индекс страницы в opaque cursor для `session/list`.

    Пример использования:
        cursor = encode_session_cursor(50)
    """

    payload = json.dumps({"index": index}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_session_cursor(cursor: str) -> int | None:
    """Декодирует opaque cursor `session/list` в индекс начала страницы.

    Возвращает `None`, если cursor поврежден или невалиден.

    Пример использования:
        index = decode_session_cursor(cursor)
    """

    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    index = payload.get("index")
    if not isinstance(index, int) or index < 0:
        return None
    return index


def build_modes_state(
    values: dict[str, str],
    config_specs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Строит состояние modes для клиентов ACP.

    Возвращает список доступных режимов (plan, standard, bypass)
    и текущий активный режим.

    Пример использования:
        modes = build_modes_state({"mode": "standard", "model": "baseline"}, specs)
    """
    from ...domain.mode import DEFAULT_MODE, MODE_DESCRIPTIONS, VALID_MODES

    available_modes = [
        {
            "id": mode_id,
            "name": MODE_DESCRIPTIONS[mode_id]["name"],
            "description": MODE_DESCRIPTIONS[mode_id]["description"],
        }
        for mode_id in sorted(VALID_MODES)
    ]

    current_mode = values.get("mode", DEFAULT_MODE)

    return {
        "availableModes": available_modes,
        "currentModeId": current_mode,
    }


def build_config_options(
    values: dict[str, str],
    config_specs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Строит wire-представление списка config options для клиента.

    Пример использования:
        options = build_config_options({"mode": "ask", "model": "baseline"}, specs)
    """

    options: list[dict[str, Any]] = []
    for config_id, spec in config_specs.items():
        options.append(
            {
                "id": config_id,
                "name": spec["name"],
                "category": spec["category"],
                "type": "select",
                "currentValue": values.get(config_id, spec["default"]),
                "options": spec["options"],
            }
        )
    return options


def session_info_notification(
    *,
    session_id: str,
    title: str | None,
    updated_at: str | None,
) -> ACPMessage:
    """Создает notification `session_info_update` для `session/update`.

    `updated_at` допускает `None`: по ACP (`04-Session List.md`) поля
    `session_info_update` опциональны, а `null` — валидное значение (очистка).
    Доменный `Session.updated_at` тоже nullable — метка не синтезируется при
    round-trip (ADR-006).

    Пример использования:
        note = session_info_notification(
            session_id="sess_1",
            title="My session",
            updated_at="2026-04-07T00:00:00Z",
        )
    """

    return ACPMessage.notification(
        "session/update",
        {
            "sessionId": session_id,
            "update": {
                "sessionUpdate": "session_info_update",
                "title": title,
                "updatedAt": updated_at,
            },
        },
    )
