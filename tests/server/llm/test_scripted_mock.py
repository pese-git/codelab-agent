"""Юнит-тесты сценарного ScriptedMockLLMProvider (конечный автомат)."""

from __future__ import annotations

import json

import pytest

from codelab.server.llm.models import CompletionRequest, LLMMessage, StopReason
from codelab.server.llm.scripted_mock import ScriptedMockLLMProvider

pytestmark = pytest.mark.asyncio


def _req(*messages: LLMMessage) -> CompletionRequest:
    return CompletionRequest(model="mock/x", messages=list(messages))


def _user(text: str) -> LLMMessage:
    return LLMMessage(role="user", content=text)


def _tool_result(call_id: str, content: str) -> LLMMessage:
    return LLMMessage(role="tool", tool_call_id=call_id, content=content)


SCENARIO = {
    "turns": [
        {"when_user": ["привет"], "replies": [{"text": "Привет!"}]},
        {
            "when_user": ["README", "прочти"],
            "replies": [
                {"tool_calls": [
                    {"name": "fs_read_text_file", "arguments": {"path": "README.md"}}
                ]},
                {"text": "Готово."},
            ],
        },
    ],
    "default": {"text": "Не понял."},
}


async def test_simple_text_turn():
    p = ScriptedMockLLMProvider.from_dict(SCENARIO)
    r = await p.create_completion(_req(_user("привет")))
    assert r.text == "Привет!"
    assert r.stop_reason == StopReason.END_TURN
    assert r.tool_calls == []


async def test_tool_then_final_sequence():
    p = ScriptedMockLLMProvider.from_dict(SCENARIO)

    # Первый вызов на пользовательский промпт → tool call
    r1 = await p.create_completion(_req(_user("прочти README.md")))
    assert r1.stop_reason == StopReason.TOOL_USE
    assert len(r1.tool_calls) == 1
    assert r1.tool_calls[0].name == "fs_read_text_file"
    call_id = r1.tool_calls[0].id

    # После tool-результата → финальный текст
    r2 = await p.create_completion(
        _req(
            _user("прочти README.md"),
            LLMMessage(role="assistant", tool_calls=r1.tool_calls),
            _tool_result(call_id, "file data"),
        )
    )
    assert r2.stop_reason == StopReason.END_TURN
    assert r2.text == "Готово."


async def test_default_reply_for_unmatched():
    p = ScriptedMockLLMProvider.from_dict(SCENARIO)
    r = await p.create_completion(_req(_user("что-то незнакомое")))
    assert r.text == "Не понял."


async def test_matching_is_case_insensitive_substring():
    p = ScriptedMockLLMProvider.from_dict(SCENARIO)
    r = await p.create_completion(_req(_user("ПРИВЕТ, агент!")))
    assert r.text == "Привет!"


async def test_from_file(tmp_path):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(SCENARIO), encoding="utf-8")
    p = ScriptedMockLLMProvider.from_file(path)
    r = await p.create_completion(_req(_user("привет")))
    assert r.text == "Привет!"


async def test_terminal_id_placeholder_resolution():
    scenario = {
        "turns": [
            {
                "when_user": ["ls"],
                "replies": [
                    {"tool_calls": [
                        {"name": "terminal_create", "arguments": {"command": "ls"}}
                    ]},
                    {"tool_calls": [
                        {"name": "terminal_wait_for_exit",
                         "arguments": {"terminalId": "${terminal_id}"}}
                    ]},
                    {"text": "done"},
                ],
            }
        ]
    }
    p = ScriptedMockLLMProvider.from_dict(scenario)
    r1 = await p.create_completion(_req(_user("ls")))
    assert r1.tool_calls[0].name == "terminal_create"

    # Tool-результат содержит terminalId — плейсхолдер должен подставиться
    r2 = await p.create_completion(
        _req(
            _user("ls"),
            LLMMessage(role="assistant", tool_calls=r1.tool_calls),
            _tool_result(r1.tool_calls[0].id, '{"terminalId": "term-42"}'),
        )
    )
    assert r2.tool_calls[0].name == "terminal_wait_for_exit"
    assert r2.tool_calls[0].arguments["terminalId"] == "term-42"


async def test_default_response_when_no_scenario():
    p = ScriptedMockLLMProvider()
    r = await p.create_completion(_req(_user("что угодно")))
    assert r.text == "Mock response"
    assert r.stop_reason == StopReason.END_TURN
