"""Тесты для AgentLoop."""

from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from codelab.server.agent.core.agent_base import AgentResponse
from codelab.server.domain.session import TurnState
from codelab.server.messages import ACPMessage
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import (
    AgentLoop,
    AgentLoopResult,
    ToolProcessingResult,
)
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.stop_reasons import StopReason
from codelab.server.tools.base import ToolExecutionResult
from tests.server._domain_sessions import make_commands, make_domain_session, wire_history


@pytest.fixture
def mock_strategy():
    """Mock LLMCallStrategy."""
    strategy = MagicMock()
    strategy.execute = AsyncMock()
    strategy.continue_execution = AsyncMock()
    return strategy


@pytest.fixture
def session():
    """Настоящий доменный агрегат сессии.

    Мока здесь быть не может: turn пишет состояние командами, а команда
    загружает сессию из хранилища в момент применения. Мок отвечает на любой
    вызов, поэтому «команда не доехала» на нём неотличима от «команда
    применилась» — ровно тот класс, что скрывал дефекты цепочки `tools/`
    (ADR-006, фаза D шаг 3) и потерю записей (P1-49).
    """
    return make_domain_session(session_id="test_session", cwd="/tmp", mcp_servers=[])


@pytest.fixture
def mock_dependencies():
    """Mock зависимости AgentLoop."""
    mock_spb = MagicMock()
    mock_spb.build.return_value = "You are a helpful assistant."
    return {
        "tool_registry": MagicMock(),
        # `wraps` вместо чистой заглушки: ответ модели и его запись в журнал
        # неразделимы и живут в `ToolCallHandler.answer_tool_call` (ADR-008,
        # шаг 4), поэтому подменённая дверь превращала «ответ записан» в
        # «заглушка вызвана» — тот же класс, что описан у фикстуры `session`.
        # Настройки вида `create_tool_call.return_value` продолжают работать.
        "tool_call_handler": MagicMock(wraps=ToolCallHandler()),
        "permission_manager": MagicMock(),
        "state_manager": MagicMock(),
        "content_extractor": AsyncMock(),
        "content_validator": MagicMock(),
        "history_writer": MagicMock(),
        "plan_builder": MagicMock(),
        "system_prompt_builder": mock_spb,
    }


class TestAgentLoopResult:
    """Тесты AgentLoopResult."""

    def test_default_values(self):
        """AgentLoopResult имеет правильные значения по умолчанию."""
        result = AgentLoopResult()
        assert result.text is None
        assert result.stop_reason == StopReason.END_TURN
        assert result.notifications == []
        assert result.pending_permission is False
        assert result.pending_tool_calls == []
        assert result.tool_results == []

    def test_custom_values(self):
        """AgentLoopResult принимает кастомные значения."""
        result = AgentLoopResult(
            text="Hello",
            stop_reason=StopReason.MAX_TURN_REQUESTS,
            pending_permission=True,
        )
        assert result.text == "Hello"
        assert result.stop_reason == StopReason.MAX_TURN_REQUESTS
        assert result.pending_permission is True


class TestToolProcessingResult:
    """Тесты ToolProcessingResult."""

    def test_default_values(self):
        """ToolProcessingResult имеет правильные значения по умолчанию."""
        result = ToolProcessingResult()
        assert result.tool_results == []
        assert result.pending_permission is False
        assert result.pending_tool_calls == []


class TestAgentLoop:
    """Тесты AgentLoop."""

    @pytest.mark.asyncio
    async def test_run_no_tool_calls(self, mock_strategy, session, mock_dependencies):
        """run() завершается без tool_calls."""
        from codelab.server.agent.core.agent_base import AgentResponse

        mock_response = MagicMock(spec=AgentResponse)
        mock_response.text = "Hello!"
        mock_response.tool_calls = []
        mock_strategy.execute.return_value = mock_response

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Hello")

        assert result.text == "Hello!"
        assert result.stop_reason == StopReason.END_TURN
        mock_strategy.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_max_turn_requests(self, mock_strategy, session, mock_dependencies):
        """run() достигает max_turn_requests."""
        from codelab.server.agent.core.agent_base import AgentResponse

        # Создаём response с tool_calls
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "test_tool"
        mock_tool_call.arguments = {}

        mock_response = MagicMock(spec=AgentResponse)
        mock_response.text = ""
        mock_response.tool_calls = [mock_tool_call]
        mock_strategy.execute.return_value = mock_response
        mock_strategy.continue_execution.return_value = mock_response

        # Mock tool execution — tool не требует permission
        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tool_1"
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_call_notification.return_value = MagicMock()
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_update_notification.return_value = MagicMock()

        # Mock tool execution result
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "Success"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool.return_value = mock_tool_result

        # Mock content extraction
        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies, max_turn_requests=2)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Hello")

        assert result.stop_reason == StopReason.MAX_TURN_REQUESTS

    @pytest.mark.asyncio
    async def test_run_cancellation(self, mock_strategy, session, mock_dependencies):
        """run() обрабатывает отмену."""
        session.active_turn = TurnState(session_id="test_session", cancel_requested=True)

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Hello")

        assert result.stop_reason == StopReason.CANCELLED

    @pytest.mark.asyncio
    async def test_run_with_tool_calls_completes(
        self, mock_strategy, session, mock_dependencies
    ):
        """run() выполняет tool_calls и завершается с END_TURN."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "test_tool"
        mock_tool_call.arguments = {"arg": "value"}

        # Первая итерация: response с tool_calls
        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Using tool..."
        first_response.tool_calls = [mock_tool_call]

        # Вторая итерация: response без tool_calls (завершение)
        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Done!"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        # Настройка tool execution
        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_call_notification.return_value = MagicMock()
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_update_notification.return_value = MagicMock()

        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "Tool output"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool.return_value = mock_tool_result

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Hello")

        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "Done!"
        mock_strategy.execute.assert_called_once()
        mock_strategy.continue_execution.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_permission_pause(self, mock_strategy, session, mock_dependencies):
        """run() приостанавливается при запросе permission."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "dangerous_tool"
        mock_tool_call.arguments = {}

        mock_response = MagicMock(spec=AgentResponse)
        mock_response.text = "Need permission"
        mock_response.tool_calls = [mock_tool_call]
        mock_strategy.execute.return_value = mock_response

        # Tool требует permission
        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = True
        mock_tool_def.kind = "terminal"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_call_notification.return_value = MagicMock()

        # Permission manager возвращает request
        mock_dependencies["permission_manager"].build_permission_request.return_value = MagicMock()

        # active_turn для установки phase
        session.active_turn = TurnState(session_id="test_session", cancel_requested=False)

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Do something")

        assert result.pending_permission is True
        assert "tc_1" in result.pending_tool_calls

    @pytest.mark.asyncio
    async def test_resume_after_permission(self, mock_strategy, session, mock_dependencies):
        """resume_after_permission() выполняет pending tool и продолжает цикл."""
        # Настройка tool_call_state
        stored_call = session.tool_calls.create(
            tool_name="test_tool",
            arguments={"arg": "value"},
            tool_call_id_from_llm="call_1",
        )

        # Tool execution result
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "Success"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool.return_value = mock_tool_result

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        # После resume — LLM отвечает без tool_calls
        final_response = MagicMock(spec=AgentResponse)
        final_response.text = "Completed!"
        final_response.tool_calls = []
        mock_strategy.continue_execution.return_value = final_response

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.resume_after_permission(commands, "test_session", stored_call.id)

        assert result.stop_reason == StopReason.END_TURN
        mock_dependencies["tool_registry"].execute_tool.assert_called_once()
        mock_strategy.continue_execution.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_after_permission_tool_not_found(
        self, mock_strategy, session, mock_dependencies
    ):
        """resume_after_permission() возвращает END_TURN если tool не найден."""
        # Реестр вызовов пуст — tool не найден

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.resume_after_permission(commands, "test_session", "nonexistent_tc")

        assert result.stop_reason == StopReason.END_TURN
        mock_dependencies["tool_registry"].execute_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_llm_error(self, mock_strategy, session, mock_dependencies):
        """run() обрабатывает ошибку LLM и возвращает END_TURN."""
        mock_strategy.execute.side_effect = RuntimeError("LLM unavailable")

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Hello")

        assert result.stop_reason == StopReason.END_TURN
        assert len(result.notifications) == 1

    @pytest.mark.asyncio
    async def test_run_tool_execution_error(self, mock_strategy, session, mock_dependencies):
        """run() обрабатывает ошибку выполнения tool и продолжает цикл."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "failing_tool"
        mock_tool_call.arguments = {}

        # Первая итерация: tool_calls
        first_response = MagicMock(spec=AgentResponse)
        first_response.text = ""
        first_response.tool_calls = [mock_tool_call]

        # Вторая итерация: завершение
        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Recovered"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_call_notification.return_value = MagicMock()
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_update_notification.return_value = MagicMock()

        # Tool выбрасывает исключение
        mock_dependencies["tool_registry"].execute_tool.side_effect = RuntimeError("Tool crash")

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Try tool")

        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "Recovered"

    @pytest.mark.asyncio
    async def test_run_with_plan(self, mock_strategy, session, mock_dependencies):
        """run() обрабатывает plan из ответа LLM."""
        mock_plan = [{"id": "1", "content": "Step 1"}]

        mock_response = MagicMock(spec=AgentResponse)
        mock_response.text = "Here is my plan"
        mock_response.tool_calls = []
        mock_response.plan = mock_plan
        mock_strategy.execute.return_value = mock_response

        mock_dependencies["plan_builder"].validate_plan_entries.return_value = mock_plan
        mock_dependencies["plan_builder"].build_plan_notification.return_value = MagicMock()

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Plan this")

        assert result.stop_reason == StopReason.END_TURN
        mock_dependencies["plan_builder"].validate_plan_entries.assert_called_once_with(mock_plan)
        mock_dependencies["history_writer"].save_plan.assert_called_once()

    @pytest.mark.asyncio
    async def test_first_iteration_uses_execute(
        self, mock_strategy, session, mock_dependencies
    ):
        """Первая итерация вызывает strategy.execute()."""
        mock_response = MagicMock(spec=AgentResponse)
        mock_response.text = "Response"
        mock_response.tool_calls = []
        mock_strategy.execute.return_value = mock_response

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        await loop.run(commands, "test_session", "Initial prompt")

        # Ядро читает сессию через порт `SessionView`, поэтому в стратегию уходит
        # проекция агрегата, а не сам агрегат (ADR-006, шаг 2 фазы D).
        mock_strategy.execute.assert_called_once_with(
            ANY,
            "Initial prompt",
            None,
            system_prompt="You are a helpful assistant.",
            on_delta=None,
        )
        assert mock_strategy.execute.call_args.args[0]._session is session
        mock_strategy.continue_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_subsequent_iterations_use_continue_execution(
        self, mock_strategy, session, mock_dependencies
    ):
        """Последующие итерации вызывают strategy.continue_execution()."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "test_tool"
        mock_tool_call.arguments = {}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = ""
        first_response.tool_calls = [mock_tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Final"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_call_notification.return_value = MagicMock()
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_update_notification.return_value = MagicMock()

        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "OK"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool.return_value = mock_tool_result

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        await loop.run(commands, "test_session", "Start")

        mock_strategy.execute.assert_called_once()
        mock_strategy.continue_execution.assert_called_once_with(ANY, None, on_delta=None)
        assert mock_strategy.continue_execution.call_args.args[0]._session is session

    def test_add_tool_result_to_history_success(
        self, mock_strategy, session, mock_dependencies
    ):
        """_add_tool_result_to_history() добавляет успешный результат."""
        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        loop._tool_processor._add_tool_result_to_history(
            session, "tc_1", success=True, output="Result text", error=None
        )

        assert len(wire_history(session)) == 1
        assert wire_history(session)[0] == {
            "role": "tool",
            "tool_call_id": "tc_1",
            "content": "Result text",
        }

    def test_add_tool_result_to_history_failure(
        self, mock_strategy, session, mock_dependencies
    ):
        """_add_tool_result_to_history() добавляет ошибку."""
        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        loop._tool_processor._add_tool_result_to_history(
            session, "tc_1", success=False, output=None, error="Something failed"
        )

        assert len(wire_history(session)) == 1
        assert wire_history(session)[0] == {
            "role": "tool",
            "tool_call_id": "tc_1",
            "content": "Something failed",
        }

    def test_history_gains_description_of_non_text_blocks(
        self, mock_strategy, session, mock_dependencies
    ):
        """Нетекстовый блок оставляет след в истории (такт 1 `multimodal-tool-results`).

        До правки такой блок исчезал бесследно: модель получала только `output` исполнителя, а
        изображение не упоминалось нигде. Описание дописывается к тексту, а не заменяет его.
        """
        from codelab.server.protocol.content.extractor import ExtractedContent

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        extracted = ExtractedContent(
            tool_call_id="tc_1",
            content_items=[
                {"type": "text", "text": "график построен"},
                {"type": "image", "data": "BASE64", "mimeType": "image/png"},
            ],
            has_content=True,
        )

        loop._tool_processor._add_tool_result_to_history(
            session,
            "tc_1",
            success=True,
            output="график построен",
            error=None,
            extracted_content=extracted,
        )

        assert wire_history(session)[0]["content"] == "график построен\n\n[Image: image/png]"

    def test_history_never_gains_base64(self, mock_strategy, session, mock_dependencies):
        """Инвариант такта 1: данные не попадают в документ сессии.

        Гейт стоит на wire-форме истории — именно она уезжает на диск, и именно её рост цена
        решения Р2 отложила до шага C расщепления.
        """
        from codelab.server.protocol.content.extractor import ExtractedContent

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        extracted = ExtractedContent(
            tool_call_id="tc_1",
            content_items=[
                {"type": "image", "data": "СЕКРЕТНЫЙ_BASE64", "mimeType": "image/png"}
            ],
            has_content=True,
        )

        loop._tool_processor._add_tool_result_to_history(
            session, "tc_1", success=True, output=None, error=None, extracted_content=extracted
        )

        assert "СЕКРЕТНЫЙ_BASE64" not in str(wire_history(session))
        assert wire_history(session)[0]["content"] == "Success\n\n[Image: image/png]"

    def test_text_only_result_is_untouched_by_the_describer(
        self, mock_strategy, session, mock_dependencies
    ):
        """Опорная точка: текстовый результат такт 1 менять не должен.

        `output` исполнителя остаётся единственным содержимым — строка не переупаковывается через
        рендер, иначе поехал бы payload и с ним prompt cache.
        """
        from codelab.server.protocol.content.extractor import ExtractedContent

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        extracted = ExtractedContent(
            tool_call_id="tc_1",
            content_items=[{"type": "text", "text": "иной текст, чем в output"}],
            has_content=True,
        )

        loop._tool_processor._add_tool_result_to_history(
            session,
            "tc_1",
            success=True,
            output="текст исполнителя",
            error=None,
            extracted_content=extracted,
        )

        assert wire_history(session)[0]["content"] == "текст исполнителя"

    def test_terminal_block_adds_nothing(self, mock_strategy, session, mock_dependencies):
        """`terminal` — клиентский дескриптор: alias модель уже получила в `output`."""
        from codelab.server.protocol.content.extractor import ExtractedContent

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        extracted = ExtractedContent(
            tool_call_id="tc_1",
            content_items=[
                {"type": "terminal", "terminalId": "client-uuid"},
                {"type": "content", "content": {"type": "text", "text": "Terminal term_1 created"}},
            ],
            has_content=True,
        )

        loop._tool_processor._add_tool_result_to_history(
            session,
            "tc_1",
            success=True,
            output="Терминал создан с ID: term_1",
            error=None,
            extracted_content=extracted,
        )

        assert wire_history(session)[0]["content"] == "Терминал создан с ID: term_1"

    def test_add_tool_result_to_history_failure_no_error(
        self, mock_strategy, session, mock_dependencies
    ):
        """_add_tool_result_to_history() использует дефолтное сообщение при отсутствии error."""
        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        loop._tool_processor._add_tool_result_to_history(
            session, "tc_1", success=False, output=None, error=None
        )

        assert wire_history(session)[0]["content"] == "Tool execution failed"

    def test_add_tool_result_to_history_failure_preserves_output(
        self, mock_strategy, session, mock_dependencies
    ):
        """Неуспех (ненулевой exit code) НЕ теряет output — LLM видит результат команды.

        Регресс: `flutter analyze` возвращает exit code 1 + список проблем в output;
        раньше в историю попадало 'Tool execution failed', и агент не знал, что чинить.
        """
        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        analyze_output = "9 issues found. error • Missing concrete implementation ..."

        loop._tool_processor._add_tool_result_to_history(
            session, "tc_1", success=False, output=analyze_output, error=None
        )

        assert wire_history(session)[0]["content"] == analyze_output

    def test_add_tool_result_to_history_failure_combines_output_and_error(
        self, mock_strategy, session, mock_dependencies
    ):
        """При наличии и output, и error в историю попадают оба."""
        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        loop._tool_processor._add_tool_result_to_history(
            session, "tc_1", success=False, output="partial output", error="boom"
        )

        content = wire_history(session)[0]["content"]
        assert "partial output" in content
        assert "boom" in content

    def test_is_cancel_requested_true(self, mock_strategy, session, mock_dependencies):
        """_is_cancel_requested() возвращает True при cancel_requested."""
        session.active_turn = TurnState(session_id="test_session", cancel_requested=True)

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        assert loop._is_cancel_requested(session, 0, "test_session") is True

    def test_is_cancel_requested_true_on_registry_generation_change(
        self, mock_strategy, session, mock_dependencies
    ):
        """Отмена в процессном реестре видна, даже если active_turn очищен (P0-39)."""
        from codelab.server.protocol.turn_cancellation import TurnCancellationRegistry

        registry = TurnCancellationRegistry()
        session.active_turn = None
        registry.cancel("test_session")

        loop = AgentLoop(strategy=mock_strategy, turn_cancellation=registry, **mock_dependencies)
        assert loop._is_cancel_requested(session, 0, "test_session") is True

    def test_is_cancel_requested_false_no_active_turn(
        self, mock_strategy, session, mock_dependencies
    ):
        """_is_cancel_requested() возвращает False при отсутствии active_turn."""
        session.active_turn = None

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        assert loop._is_cancel_requested(session, 0, "test_session") is False

    def test_is_cancel_requested_false_not_cancelled(
        self, mock_strategy, session, mock_dependencies
    ):
        """_is_cancel_requested() возвращает False когда cancel_requested=False."""
        session.active_turn = TurnState(session_id="test_session", cancel_requested=False)

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        assert loop._is_cancel_requested(session, 0, "test_session") is False

    @pytest.mark.asyncio
    async def test_run_cancellation_during_tool_processing(
        self, mock_strategy, session, mock_dependencies
    ):
        """run() обрабатывает отмену во время обработки tool_calls."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "slow_tool"
        mock_tool_call.arguments = {}

        mock_response = MagicMock(spec=AgentResponse)
        mock_response.text = ""
        mock_response.tool_calls = [mock_tool_call]
        mock_strategy.execute.return_value = mock_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_call_notification.return_value = MagicMock()

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        # Патчим _is_cancel_requested: первые 2 вызова — False, затем True
        call_count = 0

        def cancel_side_effect(session, started_epoch, session_id=None):
            nonlocal call_count
            call_count += 1
            return call_count > 2

        loop._is_cancel_requested = MagicMock(side_effect=cancel_side_effect)

        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Start")

        assert result.stop_reason == StopReason.CANCELLED

    @pytest.mark.asyncio
    async def test_run_tool_rejected_by_policy(
        self, mock_strategy, session, mock_dependencies
    ):
        """run() обрабатывает отклонение tool политикой."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "blocked_tool"
        mock_tool_call.arguments = {}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = ""
        first_response.tool_calls = [mock_tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Handled rejection"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = True
        mock_tool_def.kind = "terminal"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_call_notification.return_value = MagicMock()
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_update_notification.return_value = MagicMock()

        # Политика отклоняет
        session.permissions.policy = {"terminal": "reject_always"}

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Try blocked")

        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "Handled rejection"

    @pytest.mark.asyncio
    async def test_update_plan_tool_sends_plan_notification(
        self, mock_strategy, session, mock_dependencies
    ):
        """update_plan tool отправляет plan notification клиенту."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "update_plan"
        mock_tool_call.arguments = {
            "entries": [
                {"content": "Step 1", "priority": "high", "status": "pending"},
                {"content": "Step 2", "priority": "medium", "status": "pending"},
            ]
        }

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Updating plan"
        first_response.tool_calls = [mock_tool_call]
        first_response.plan = None
        first_response.stop_reason = None
        first_response.usage = None
        mock_strategy.execute.return_value = first_response

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Done"
        second_response.tool_calls = []
        second_response.plan = None
        second_response.stop_reason = None
        second_response.usage = None
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.kind = "think"
        mock_tool_def.requires_permission = False
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        handler = mock_dependencies["tool_call_handler"]
        handler.build_tool_call_notification.return_value = MagicMock()
        handler.build_tool_update_notification.return_value = MagicMock()

        validated_entries = [
            {"content": "Step 1", "priority": "high", "status": "pending"},
            {"content": "Step 2", "priority": "medium", "status": "pending"},
        ]
        exec_result = ToolExecutionResult(
            success=True,
            output="Plan updated with 2 entries",
            metadata={"validated_entries": validated_entries},
        )
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(return_value=exec_result)

        plan_notification = ACPMessage.notification(
            "session/update",
            {
                "sessionId": "test_session",
                "update": {
                    "sessionUpdate": "plan",
                    "entries": validated_entries,
                },
            },
        )
        mock_dependencies["plan_builder"].build_plan_notification.return_value = plan_notification

        session.tool_calls.create(
            tool_name="test_tool",
            arguments={},
            tool_call_id_from_llm="call_1",
        )

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted
        mock_dependencies["content_validator"].validate_content_list.return_value = (True, [])

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Update plan")

        plan_notifications = [
            n
            for n in result.notifications
            if n.params and n.params.get("update", {}).get("sessionUpdate") == "plan"
        ]
        assert len(plan_notifications) == 1
        mock_dependencies["plan_builder"].build_plan_notification.assert_called_once_with(
            "test_session", validated_entries
        )
        mock_dependencies["history_writer"].save_plan.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_plan_tool_invalid_entries_no_notification(
        self, mock_strategy, session, mock_dependencies
    ):
        """update_plan tool с невалидными entries не отправляет plan notification."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "update_plan"
        mock_tool_call.arguments = {"entries": []}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Updating plan"
        first_response.tool_calls = [mock_tool_call]
        first_response.plan = None
        first_response.stop_reason = None
        first_response.usage = None
        mock_strategy.execute.return_value = first_response

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Done"
        second_response.tool_calls = []
        second_response.plan = None
        second_response.stop_reason = None
        second_response.usage = None
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.kind = "think"
        mock_tool_def.requires_permission = False
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        handler2 = mock_dependencies["tool_call_handler"]
        handler2.build_tool_call_notification.return_value = MagicMock()
        handler2.build_tool_update_notification.return_value = MagicMock()

        exec_result = ToolExecutionResult(
            success=True,
            output="Plan updated with 0 entries",
            metadata={"validated_entries": []},
        )
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(return_value=exec_result)

        session.tool_calls.create(
            tool_name="test_tool",
            arguments={},
            tool_call_id_from_llm="call_1",
        )

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted
        mock_dependencies["content_validator"].validate_content_list.return_value = (True, [])

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Update plan")

        plan_notifications = [
            n
            for n in result.notifications
            if n.params and n.params.get("update", {}).get("sessionUpdate") == "plan"
        ]
        assert len(plan_notifications) == 0
        mock_dependencies["plan_builder"].build_plan_notification.assert_not_called()


class TestAgentLoopBypassMode:
    """Тесты AgentLoop в bypass mode — инструменты выполняются без permission."""

    @pytest.mark.asyncio
    async def test_bypass_mode_tool_executes_and_loop_continues(
        self, mock_strategy, session, mock_dependencies
    ):
        """В bypass mode tool выполняется синхронно, цикл продолжает и LLM возвращает ответ."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "fs_read_text_file"
        mock_tool_call.arguments = {"path": "README.md"}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Reading file..."
        first_response.tool_calls = [mock_tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "File contains: Hello World"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        # Tool не требует permission (bypass mode)
        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "read"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        h = mock_dependencies["tool_call_handler"]
        h.build_tool_call_notification.return_value = MagicMock()
        h.build_tool_update_notification.return_value = MagicMock()

        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "Hello World"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool.return_value = mock_tool_result

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        # Bypass mode в config
        session.set_config_value("mode", "bypass")

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Read README.md")

        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "File contains: Hello World"
        mock_strategy.execute.assert_called_once()
        mock_strategy.continue_execution.assert_called_once()

    @pytest.mark.asyncio
    async def test_bypass_mode_multiple_tool_calls(
        self, mock_strategy, session, mock_dependencies
    ):
        """В bypass mode несколько tool calls выполняются последовательно."""
        mock_tool_call_1 = MagicMock()
        mock_tool_call_1.id = "call_1"
        mock_tool_call_1.name = "fs_read_text_file"
        mock_tool_call_1.arguments = {"path": "file1.txt"}

        mock_tool_call_2 = MagicMock()
        mock_tool_call_2.id = "call_2"
        mock_tool_call_2.name = "fs_read_text_file"
        mock_tool_call_2.arguments = {"path": "file2.txt"}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Reading files..."
        first_response.tool_calls = [mock_tool_call_1, mock_tool_call_2]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Both files read successfully"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "read"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        h = mock_dependencies["tool_call_handler"]
        h.build_tool_call_notification.return_value = MagicMock()
        h.build_tool_update_notification.return_value = MagicMock()

        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "File content"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool.return_value = mock_tool_result

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        session.set_config_value("mode", "bypass")

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Read both files")

        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "Both files read successfully"
        assert mock_strategy.execute.call_count == 1
        assert mock_strategy.continue_execution.call_count == 1

    @pytest.mark.asyncio
    async def test_bypass_mode_tool_requires_permission_but_mode_allows(
        self, mock_strategy, session, mock_dependencies
    ):
        """В bypass mode tool с requires_permission=True выполняется без запроса."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "terminal_create"
        mock_tool_call.arguments = {"command": "ls"}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Running command..."
        first_response.tool_calls = [mock_tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Command completed"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        # Tool требует permission, но bypass mode должен разрешить
        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = True
        mock_tool_def.kind = "execute"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        h = mock_dependencies["tool_call_handler"]
        h.build_tool_call_notification.return_value = MagicMock()
        h.build_tool_update_notification.return_value = MagicMock()

        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "total 100"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool.return_value = mock_tool_result

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        session.set_config_value("mode", "bypass")
        session.active_turn = TurnState(session_id="test_session", cancel_requested=False)

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Run ls")

        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "Command completed"
        # Permission manager НЕ должен быть вызван в bypass mode
        mock_dependencies["permission_manager"].build_permission_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_bypass_mode_tool_error_continues_loop(
        self, mock_strategy, session, mock_dependencies
    ):
        """В bypass mode ошибка инструмента не прерывает цикл."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "fs_read_text_file"
        mock_tool_call.arguments = {"path": "nonexistent.txt"}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Trying to read..."
        first_response.tool_calls = [mock_tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "File not found, sorry"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "read"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        h = mock_dependencies["tool_call_handler"]
        h.build_tool_call_notification.return_value = MagicMock()
        h.build_tool_update_notification.return_value = MagicMock()

        # Tool execution fails
        mock_tool_result = MagicMock()
        mock_tool_result.success = False
        mock_tool_result.output = None
        mock_tool_result.error = "File not found"
        mock_dependencies["tool_registry"].execute_tool.return_value = mock_tool_result

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        session.set_config_value("mode", "bypass")

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Read file")

        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "File not found, sorry"
        mock_strategy.continue_execution.assert_called_once()


class TestAgentLoopNotificationCallback:
    """Тесты для immediate notification delivery через callback."""

    def test_set_notification_callback_updates_callback(self, mock_strategy, mock_dependencies):
        """set_notification_callback обновляет callback в AgentLoop."""
        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        # Изначально callback равен None
        assert loop._notification_callback is None

        # Устанавливаем callback
        async def mock_callback(msg):
            pass

        loop.set_notification_callback(mock_callback)
        assert loop._notification_callback is mock_callback

        # Можно установить None
        loop.set_notification_callback(None)
        assert loop._notification_callback is None

    @pytest.mark.asyncio
    async def test_notification_callback_called_for_tool_call(
        self, mock_strategy, session, mock_dependencies
    ):
        """Callback вызывается для tool call notification."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "fs_read_text_file"
        mock_tool_call.arguments = {"path": "test.txt"}

        response = MagicMock(spec=AgentResponse)
        response.text = "Reading file..."
        response.tool_calls = [mock_tool_call]

        mock_strategy.execute.return_value = response
        # Второй виток цикла обязан вернуть настоящий ответ: его текст уезжает в
        # историю и дальше в wire.
        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Done"
        second_response.tool_calls = []
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "read"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        h = mock_dependencies["tool_call_handler"]
        h.build_tool_call_notification.return_value = MagicMock()
        h.build_tool_update_notification.return_value = MagicMock()

        # Настоящий результат исполнения, а не мок: его поля уезжают в историю и
        # дальше в wire — на моке туда попадал бы объект мока, а не текст.
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(
            return_value=ToolExecutionResult(success=True, output="File content")
        )

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        # Создаём callback и передаём в AgentLoop
        sent_notifications = []

        async def mock_callback(msg):
            sent_notifications.append(msg)

        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=mock_callback,
        )

        # Запускаем loop с tool call
        commands = make_commands(session)
        await loop.run(commands, "test_session", "Read file")

        # Проверяем что callback был вызван для tool call notification
        assert len(sent_notifications) > 0, "Callback должен быть вызван хотя бы один раз"

    @pytest.mark.asyncio
    async def test_tool_exception_delivers_failed_update_immediately(
        self, mock_strategy, session, mock_dependencies
    ):
        """P2-25: при исключении tool'а failed-update уходит через callback сразу.

        Раньше exception-ветка буферизовала notification, минуя immediate callback
        (в отличие от success-ветки) — карточка tool'а флипалась в failed только в
        конце turn'а. Фикс: exception-ветка тоже emit'ит немедленно.
        """
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "failing_tool"
        mock_tool_call.arguments = {}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = ""
        first_response.tool_calls = [mock_tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Recovered"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        h = mock_dependencies["tool_call_handler"]
        h.build_tool_call_notification.return_value = MagicMock()
        # Отличимый sentinel именно для failed-update, чтобы проверить его доставку.
        failed_update = MagicMock(name="failed_update_notification")
        h.build_tool_update_notification.return_value = failed_update

        # Tool выбрасывает исключение → exception-ветка _execute_allowed_tool_call.
        mock_dependencies["tool_registry"].execute_tool.side_effect = RuntimeError("Tool crash")

        sent_notifications = []

        async def mock_callback(msg):
            sent_notifications.append(msg)

        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=mock_callback,
        )

        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Try tool")

        # failed-update доставлен НЕМЕДЛЕННО через callback (а не только в буфере).
        assert failed_update in sent_notifications
        # И не осел в буфере (buffer = только не доставленные callback'ом).
        assert failed_update not in result.notifications

    @pytest.mark.asyncio
    async def test_notification_callback_error_does_not_break_loop(
        self, mock_strategy, session, mock_dependencies
    ):
        """Ошибка в callback не прерывает AgentLoop."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "fs_read_text_file"
        mock_tool_call.arguments = {"path": "test.txt"}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Reading file..."
        first_response.tool_calls = [mock_tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Done reading"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "read"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        h = mock_dependencies["tool_call_handler"]
        h.build_tool_call_notification.return_value = MagicMock()
        h.build_tool_update_notification.return_value = MagicMock()

        # Настоящий результат исполнения, а не мок: его поля уезжают в историю и
        # дальше в wire — на моке туда попадал бы объект мока, а не текст.
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(
            return_value=ToolExecutionResult(success=True, output="File content")
        )

        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        # Создаём callback который всегда падает
        async def failing_callback(msg):
            raise RuntimeError("Callback failed!")

        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=failing_callback,
        )

        # Loop должен завершиться успешно несмотря на ошибку в callback
        commands = make_commands(session)
        result = await loop.run(commands, "test_session", "Read file")

        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "Done reading"


def _chunk_texts(captured: list) -> list[str]:
    """Извлечь тексты agent_message_chunk из перехваченных нотификаций."""
    texts = []
    for msg in captured:
        update = (msg.params or {}).get("update", {})
        if update.get("sessionUpdate") == "agent_message_chunk":
            texts.append(update.get("content", {}).get("text", ""))
    return texts


class TestAgentLoopStreaming:
    """Живой стриминг (streaming_enabled) через on_delta."""

    @pytest.mark.asyncio
    async def test_streaming_emits_deltas_no_full_text_dup(
        self, mock_strategy, session, mock_dependencies
    ):
        """Дельты эмитятся как agent_message_chunk; полный текст не дублируется."""
        captured: list = []

        async def capture(msg: ACPMessage) -> None:
            captured.append(msg)

        async def exec_side_effect(
            session, prompt, mcp_manager, *, system_prompt=None, on_delta=None
        ):
            if on_delta:
                await on_delta("Hel")
                await on_delta("lo")
            resp = MagicMock(spec=AgentResponse)
            resp.text = "Hello"
            resp.tool_calls = []
            return resp

        mock_strategy.execute.side_effect = exec_side_effect

        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=capture,
            streaming_enabled=True,
        )
        commands = make_commands(session)
        await loop.run(commands, "test_session", "Hi")

        # Ровно дельты, без повторного полного "Hello"
        assert _chunk_texts(captured) == ["Hel", "lo"]

    @pytest.mark.asyncio
    async def test_streaming_without_deltas_falls_back_to_full_text(
        self, mock_strategy, session, mock_dependencies
    ):
        """Стриминг включён, но провайдер не отдал дельт → эмитим полный текст."""
        captured: list = []

        async def capture(msg: ACPMessage) -> None:
            captured.append(msg)

        async def exec_side_effect(
            session, prompt, mcp_manager, *, system_prompt=None, on_delta=None
        ):
            # on_delta не вызывается (провайдер без стрима)
            resp = MagicMock(spec=AgentResponse)
            resp.text = "Whole answer"
            resp.tool_calls = []
            return resp

        mock_strategy.execute.side_effect = exec_side_effect

        loop = AgentLoop(
            strategy=mock_strategy,
            **mock_dependencies,
            notification_callback=capture,
            streaming_enabled=True,
        )
        commands = make_commands(session)
        await loop.run(commands, "test_session", "Hi")

        assert _chunk_texts(captured) == ["Whole answer"]
