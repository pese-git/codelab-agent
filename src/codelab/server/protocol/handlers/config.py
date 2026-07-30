"""Обработчики методов конфигурации сессии.

Содержит логику обработки session/set_config_option и session/set_mode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from ...domain.session import Session
from ...messages import ACPMessage, JsonRpcId
from ...storage import SessionRepository
from ..state import ProtocolOutcome
from .session import (
    build_config_options,
    build_modes_state,
    session_info_notification,
)

if TYPE_CHECKING:
    from codelab.server.llm.resolver import ModelResolver

logger = structlog.get_logger()


async def session_set_config_option(
    request_id: JsonRpcId | None,
    params: dict[str, Any],
    repository: SessionRepository,
    config_specs: dict[str, dict[str, Any]],
    model_resolver: ModelResolver | None = None,
) -> ProtocolOutcome:
    """Изменяет значение конфигурационной опции сессии.

    Транзакция работает доменным агрегатом (первый шаг фазы D ADR-006):
    рабочая модель — `domain.Session`, wire-DTO живёт только внутри
    `SessionRepository`.

    В случае успеха возвращает новый snapshot `configOptions` и отправляет
    `config_option_update` + `session_info_update`.

    Пример использования:
        outcome = await session_set_config_option(
            "req_1",
            {"sessionId": "sess_1", "configId": "mode", "value": "code"},
            repository,
            config_specs,
        )
    """

    # Конфиг опции валидируем по локальной спецификации и допустимым значениям.
    session_id = params.get("sessionId")
    config_id = params.get("configId")
    value = params.get("value")

    if not isinstance(session_id, str):
        return ProtocolOutcome(
            response=ACPMessage.error_response(
                request_id,
                code=-32602,
                message="Invalid params: sessionId is required",
            )
        )
    if not isinstance(config_id, str) or not isinstance(value, str):
        return ProtocolOutcome(
            response=ACPMessage.error_response(
                request_id,
                code=-32602,
                message="Invalid params: configId and value must be strings",
            )
        )

    spec = config_specs.get(config_id)
    if spec is None:
        return ProtocolOutcome(
            response=ACPMessage.error_response(
                request_id,
                code=-32602,
                message=f"Invalid params: unknown config option {config_id}",
            )
        )

    available_values = {
        str(option["value"])
        for option in spec["options"]
        if isinstance(option, dict) and isinstance(option.get("value"), str)
    }
    if value not in available_values:
        return ProtocolOutcome(
            response=ACPMessage.error_response(
                request_id,
                code=-32602,
                message=f"Invalid params: unsupported value {value} for {config_id}",
            )
        )

    # Валидация параметров идёт до транзакции: иначе отклонённый запрос закрывал бы
    # область коммитом, а `save_session` штампует `updated_at` — получилась бы ложная
    # «последняя активность» и перезапись всего документа на отказ (ADR-007).
    # Наблюдаемое следствие: для несуществующей сессии с неверными параметрами клиент
    # получает -32602 вместо -32001. Порядок закреплён тестом.
    async with repository.transaction(session_id) as session:
        if session is None:
            logger.warning(
                "session_config_option_session_not_found",
                session_id=session_id,
                config_id=config_id,
            )
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    request_id,
                    code=-32001,
                    message=f"Session not found: {session_id}",
                )
            )

        session.set_config_value(config_id, value)
        session.mark_updated()
        # Область закрывается коммитом; дальше нужен тот же агрегат, но уже с
        # проштампованным `updated_at` (порт синхронизирует метку обратно).
        aggregate = session

    # Инвалидировать кэш провайдера при смене модели
    if config_id == "model" and model_resolver is not None:
        model_resolver.invalidate_session(session_id)

    config_options = build_config_options(aggregate.config.config_values, config_specs)
    # Отправляем полный snapshot configOptions, чтобы клиент не делал merge вручную.
    config_notification = ACPMessage.notification(
        "session/update",
        {
            "sessionId": session_id,
            "update": {
                "sessionUpdate": "config_option_update",
                "configOptions": config_options,
            },
        },
    )

    # Запись выполнила транзакция (`repository.transaction`), отдельного save нет:
    # забыть его больше нельзя, а на отказе он не случится (ADR-007).

    # Единственная точка наблюдаемости config-транзакции: до этого успешная смена
    # опции не оставляла в логе ничего, и переключение на доменный агрегат
    # (фаза D ADR-006) нельзя было подтвердить на живом прогоне — только сверкой
    # файла сессии. `updated_at` берём после save: это метка, которая ушла на диск
    # и в session_info-нотификацию (sync-back штампа порта).
    logger.info(
        "session_config_option_changed",
        session_id=session_id,
        config_id=config_id,
        value=value,
        config_values=len(aggregate.config.config_values),
        updated_at=aggregate.updated_at,
    )

    return ProtocolOutcome(
        response=ACPMessage.response(
            request_id,
            {
                "configOptions": config_options,
                "modes": build_modes_state(aggregate.config.config_values, config_specs),
            },
        ),
        notifications=build_config_update_notifications(
            session_id=session_id,
            config_id=config_id,
            session=aggregate,
            config_notification=config_notification,
            config_specs=config_specs,
        ),
    )


async def session_set_mode(
    request_id: JsonRpcId | None,
    params: dict[str, Any],
    repository: SessionRepository,
    config_specs: dict[str, dict[str, Any]],
) -> ProtocolOutcome:
    """ACP метод смены режима через `session/set_mode`.

    Поддерживает новые значения mode: plan, standard, bypass.
    Автоматически нормализует старые значения (ask→standard, code→bypass, etc).

    Пример использования:
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "bypass"},
            repository,
            config_specs,
        )
    """
    from ..mode import VALID_MODES, normalize_mode

    session_id = params.get("sessionId")
    mode_id = params.get("modeId")
    if not isinstance(session_id, str) or not isinstance(mode_id, str):
        return ProtocolOutcome(
            response=ACPMessage.error_response(
                request_id,
                code=-32602,
                message="Invalid params: sessionId and modeId must be strings",
            )
        )

    # Нормализуем mode (backward compatibility)
    normalized_mode = normalize_mode(mode_id)

    # Валидация: если mode_id не валидный и не маппится — ошибка
    if mode_id not in VALID_MODES and mode_id not in ("ask", "code", "architect", "debug"):
        valid_list = ", ".join(sorted(VALID_MODES))
        return ProtocolOutcome(
            response=ACPMessage.error_response(
                request_id,
                code=-32602,
                message=f"Invalid params: modeId must be one of: {valid_list}",
            )
        )

    mapped = await session_set_config_option(
        request_id,
        {
            "sessionId": session_id,
            "configId": "mode",
            "value": normalized_mode,
        },
        repository,
        config_specs,
    )
    if mapped.response is None or mapped.response.error is not None:
        return mapped

    # По схеме `session/set_mode` возвращает пустой объект.
    # Уведомление current_mode_update уже отправлено через session_set_config_option.
    return ProtocolOutcome(
        response=ACPMessage.response(request_id, {}),
        notifications=mapped.notifications,
    )


def build_config_update_notifications(
    *,
    session_id: str,
    config_id: str,
    session: Session,
    config_notification: ACPMessage,
    config_specs: dict[str, dict[str, Any]],
) -> list[ACPMessage]:
    """Формирует набор notifications после обновления config option.

    Пример использования:
        notes = build_config_update_notifications(
            session_id="sess_1",
            config_id="mode",
            session=state,
            config_notification=cfg_note,
            config_specs=specs,
        )
    """

    notifications: list[ACPMessage] = [config_notification]
    if config_id == "mode":
        notifications.append(
            ACPMessage.notification(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "current_mode_update",
                        "currentModeId": session.get_config_value("mode", "ask"),
                    },
                },
            )
        )
    notifications.append(
        session_info_notification(
            session_id=session_id,
            title=None,
            updated_at=session.updated_at,
        )
    )
    return notifications
