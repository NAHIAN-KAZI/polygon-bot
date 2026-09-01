"""Tests for app/banking/routing.py: the /chat intent classifier.

The Ollama HTTP layer is mocked by monkeypatching httpx.AsyncClient.post
directly, matching this codebase's existing style (see
tests/test_taxonomy.py's FakeResponse pattern) rather than pulling in a new
test dependency like respx. No test hits a real Ollama instance.

classify() is async; driven via asyncio.run() inside sync test functions,
matching tests/test_adapter_base.py (no pytest-asyncio in this repo).
"""
import asyncio
from datetime import datetime, timezone

import httpx
import pytest

import app.banking.routing as routing
from app.banking.routing import (
    BankingService,
    Clarification,
    KbQuestion,
    UnknownService,
    _render_taxonomy,
    build_system_prompt,
    build_tools,
    classify,
)
from app.banking.session import ChatTurn


FAKE_TAXONOMY = {
    "categories": [
        {
            "id": "banking",
            "name": "Banking",
            "services": [
                {
                    "id": "accounts",
                    "name": "Accounts",
                    "subServices": [
                        {"id": "checking", "name": "Checking"},
                        {"id": "savings", "name": "Savings"},
                    ],
                },
                {
                    "id": "loans",
                    "name": "Loans",
                    "subServices": [],
                },
            ],
        },
    ]
}


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data


def _install_post_response(monkeypatch, json_data, captured_calls=None):
    async def fake_post(self, url, *args, **kwargs):
        if captured_calls is not None:
            captured_calls.append({"url": url, "kwargs": kwargs})
        return FakeResponse(json_data)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def _ollama_response(tool_calls):
    return {"message": {"tool_calls": tool_calls}}


def _tool_call(name, arguments):
    return {"function": {"name": name, "arguments": arguments}}


@pytest.fixture(autouse=True)
def fake_taxonomy(monkeypatch):
    monkeypatch.setattr(routing, "get_taxonomy", lambda: FAKE_TAXONOMY)


# --- _render_taxonomy / build_system_prompt ---------------------------------


def test_render_taxonomy_includes_nested_ids_and_names():
    rendered = _render_taxonomy(FAKE_TAXONOMY)

    assert "- banking (Banking)" in rendered
    assert "  - accounts (Accounts)" in rendered
    assert "    - checking (Checking)" in rendered
    assert "    - savings (Savings)" in rendered
    assert "  - loans (Loans)" in rendered

    # nesting order: category line precedes its services, which precede their subservices
    lines = rendered.splitlines()
    banking_idx = lines.index("- banking (Banking)")
    accounts_idx = lines.index("  - accounts (Accounts)")
    checking_idx = lines.index("    - checking (Checking)")
    assert banking_idx < accounts_idx < checking_idx


def test_build_system_prompt_embeds_rendered_taxonomy():
    prompt = build_system_prompt(FAKE_TAXONOMY)

    assert "- banking (Banking)" in prompt
    assert "    - checking (Checking)" in prompt


# --- build_tools --------------------------------------------------------------


def test_build_tools_returns_three_tools_with_expected_names():
    tools = build_tools()

    assert len(tools) == 3
    names = [t["function"]["name"] for t in tools]
    assert names == ["answer_kb_question", "route_banking_service", "ask_clarification"]


def test_build_tools_route_banking_service_schema():
    tools = build_tools()
    route_tool = next(t for t in tools if t["function"]["name"] == "route_banking_service")
    params = route_tool["function"]["parameters"]

    assert set(params["properties"].keys()) == {"category", "service", "subservice"}
    assert set(params["required"]) == {"category", "service"}
    assert "subservice" not in params["required"]


def test_build_tools_ask_clarification_schema():
    tools = build_tools()
    clarify_tool = next(t for t in tools if t["function"]["name"] == "ask_clarification")
    params = clarify_tool["function"]["parameters"]

    assert set(params["properties"].keys()) == {"question"}
    assert params["required"] == ["question"]


# --- classify -------------------------------------------------------------


def test_classify_answer_kb_question_returns_kb_question(monkeypatch):
    _install_post_response(
        monkeypatch, _ollama_response([_tool_call("answer_kb_question", {})])
    )

    result = asyncio.run(classify("How do checking accounts work?"))

    assert result == KbQuestion()


def test_classify_no_tool_calls_falls_back_to_kb_question(monkeypatch):
    _install_post_response(monkeypatch, {"message": {}})

    result = asyncio.run(classify("some ambiguous message"))

    assert result == KbQuestion()


def test_classify_ask_clarification_returns_clarification(monkeypatch):
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [_tool_call("ask_clarification", {"question": "Which account do you mean?"})]
        ),
    )

    result = asyncio.run(classify("do something with my account"))

    assert result == Clarification(question="Which account do you mean?")


def test_classify_route_banking_service_valid_path_returns_banking_service(monkeypatch):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: True)
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [
                _tool_call(
                    "route_banking_service",
                    {"category": "banking", "service": "accounts", "subservice": "checking"},
                )
            ]
        ),
    )

    result = asyncio.run(classify("show me my checking balance"))

    assert result == BankingService(category="banking", service="accounts", subservice="checking")


def test_classify_route_banking_service_invalid_path_returns_unknown_service(monkeypatch):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: False)
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [
                _tool_call(
                    "route_banking_service",
                    {"category": "banking", "service": "made-up-service"},
                )
            ]
        ),
    )

    result = asyncio.run(classify("do the made up thing"))

    assert result == UnknownService(category="banking", service="made-up-service", subservice=None)
    assert not isinstance(result, BankingService)


def test_classify_normalizes_empty_string_subservice_to_none(monkeypatch):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: True)
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [
                _tool_call(
                    "route_banking_service",
                    {"category": "banking", "service": "accounts", "subservice": ""},
                )
            ]
        ),
    )

    result = asyncio.run(classify("show me my accounts"))

    assert result.subservice is None


def test_classify_includes_recent_turns_as_prior_user_messages(monkeypatch):
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("answer_kb_question", {})]),
        captured_calls=captured_calls,
    )
    recent_turns = [
        ChatTurn(timestamp=datetime.now(timezone.utc), message="what are your hours?"),
        ChatTurn(timestamp=datetime.now(timezone.utc), message="do you have a mobile app?"),
    ]

    asyncio.run(classify("thanks, one more question", recent_turns=recent_turns))

    assert len(captured_calls) == 1
    sent_messages = captured_calls[0]["kwargs"]["json"]["messages"]
    user_texts = [m["content"] for m in sent_messages if m["role"] == "user"]
    assert "what are your hours?" in user_texts
    assert "do you have a mobile app?" in user_texts
    assert "thanks, one more question" in user_texts
    # prior turns precede the new message
    assert user_texts.index("what are your hours?") < user_texts.index("thanks, one more question")
    assert user_texts.index("do you have a mobile app?") < user_texts.index("thanks, one more question")
