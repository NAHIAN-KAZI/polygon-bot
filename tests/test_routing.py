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
    _CLARIFICATION_FALLBACK,
    BankingService,
    Clarification,
    KbQuestion,
    UnknownService,
    _coerce_payload,
    _render_taxonomy,
    build_system_prompt,
    build_tools,
    classify,
)
from app.banking.session import ChatTurn
from app.config import settings


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


def _install_post_response_sequence(monkeypatch, json_data_sequence, captured_calls=None):
    """Like _install_post_response, but returns a different response on each
    successive call -- used to drive T-23's retry-once behavior (first
    attempt, then retry) with distinct Ollama responses."""
    responses = iter(json_data_sequence)

    async def fake_post(self, url, *args, **kwargs):
        if captured_calls is not None:
            captured_calls.append({"url": url, "kwargs": kwargs})
        return FakeResponse(next(responses))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def _ollama_response(tool_calls):
    return {"message": {"tool_calls": tool_calls}}


def _tool_call(name, arguments):
    return {"function": {"name": name, "arguments": arguments}}


@pytest.fixture(autouse=True)
def fake_taxonomy(monkeypatch):
    monkeypatch.setattr(routing, "get_taxonomy", lambda: FAKE_TAXONOMY)


# --- _render_taxonomy / build_system_prompt ---------------------------------












# --- T-56: transfer-specific rule + its 4 new few-shot examples ---------------
# --- (independent prompt-content regression coverage -- the implementing -----
# --- agent live-verified behavior against a real model but did not add -------
# --- these assertions, so a future prompt edit could silently drop/reword ----
# --- the rule or an example without any test catching it). -------------------












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

    assert set(params["properties"].keys()) == {"category", "service", "subservice", "payload"}
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


def test_classify_route_banking_service_invalid_path_falls_back_to_clarification_after_retry(
    monkeypatch,
):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: False)
    _install_post_response_sequence(
        monkeypatch,
        [
            _ollama_response(
                [
                    _tool_call(
                        "route_banking_service",
                        {"category": "banking", "service": "made-up-service"},
                    )
                ]
            ),
            _ollama_response(
                [
                    _tool_call(
                        "route_banking_service",
                        {"category": "banking", "service": "still-made-up-service"},
                    )
                ]
            ),
        ],
    )

    result = asyncio.run(classify("do the made up thing"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)
    assert not isinstance(result, UnknownService)
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


def test_classify_includes_last_recent_turn_as_labeled_system_context(monkeypatch):
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("answer_kb_question", {})]),
        captured_calls=captured_calls,
    )
    recent_turns = [
        ChatTurn(
            timestamp=datetime.now(timezone.utc),
            message="I want to transfer money",
            classification={"type": "CLARIFICATION_REQUIRED", "question": "Which transfer type?"},
        ),
    ]

    asyncio.run(classify("thanks, one more question", recent_turns=recent_turns))

    assert len(captured_calls) == 1
    sent_messages = captured_calls[0]["kwargs"]["json"]["messages"]
    # the prior turn is never injected as a literal user message
    user_texts = [m["content"] for m in sent_messages if m["role"] == "user"]
    assert user_texts == ["thanks, one more question"]
    # it appears instead as a labeled, disregardable system-level context note
    system_texts = [m["content"] for m in sent_messages if m["role"] == "system"]
    assert any("I want to transfer money" in text and "Which transfer type?" in text for text in system_texts)
    # T-53: broadened from a strict "ignore this context" narrow-match instruction to a
    # general rule that still lets the classifier disregard the pending context on a
    # genuine subject change — assert the equivalent escape-hatch phrasing instead.
    assert any("genuine subject change" in text for text in system_texts)


def test_classify_uses_only_last_of_multiple_recent_turns(monkeypatch):
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("answer_kb_question", {})]),
        captured_calls=captured_calls,
    )
    recent_turns = [
        ChatTurn(timestamp=datetime.now(timezone.utc), message="what are your hours?", classification=None),
        ChatTurn(
            timestamp=datetime.now(timezone.utc),
            message="I want to transfer money",
            classification={"type": "CLARIFICATION_REQUIRED", "question": "Which transfer type?"},
        ),
    ]

    asyncio.run(classify("thanks, one more question", recent_turns=recent_turns))

    sent_messages = captured_calls[0]["kwargs"]["json"]["messages"]
    system_texts = [m["content"] for m in sent_messages if m["role"] == "system"]
    assert not any("what are your hours?" in text for text in system_texts)
    assert any("I want to transfer money" in text for text in system_texts)


def test_classify_with_no_recent_turns_adds_no_context_note(monkeypatch):
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("answer_kb_question", {})]),
        captured_calls=captured_calls,
    )

    asyncio.run(classify("what are your hours?", recent_turns=[]))

    sent_messages = captured_calls[0]["kwargs"]["json"]["messages"]
    assert len(sent_messages) == 2
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[1] == {"role": "user", "content": "what are your hours?"}


# --- classify: T-23 retry-once-then-clarify --------------------------------


def test_classify_valid_first_attempt_calls_ollama_exactly_once(monkeypatch):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: True)
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [_tool_call("route_banking_service", {"category": "banking", "service": "accounts"})]
        ),
        captured_calls=captured_calls,
    )

    result = asyncio.run(classify("show me my accounts"))

    assert result == BankingService(category="banking", service="accounts", subservice=None)
    assert len(captured_calls) == 1


def test_classify_retries_once_and_returns_banking_service_on_valid_retry(monkeypatch):
    def fake_is_valid_path(category, service, subservice=None):
        return category == "banking" and service == "accounts"

    monkeypatch.setattr(routing, "is_valid_path", fake_is_valid_path)
    captured_calls = []
    _install_post_response_sequence(
        monkeypatch,
        [
            _ollama_response(
                [_tool_call("route_banking_service", {"category": "banking", "service": "made-up"})]
            ),
            _ollama_response(
                [_tool_call("route_banking_service", {"category": "banking", "service": "accounts"})]
            ),
        ],
        captured_calls=captured_calls,
    )

    result = asyncio.run(classify("show me my made up thing"))

    assert result == BankingService(category="banking", service="accounts", subservice=None)
    assert len(captured_calls) == 2

    retry_messages = captured_calls[1]["kwargs"]["json"]["messages"]
    retry_user_texts = [m["content"] for m in retry_messages if m["role"] == "user"]
    assert any("doesn't exist" in text for text in retry_user_texts)
    retry_assistant_messages = [m for m in retry_messages if m["role"] == "assistant"]
    assert len(retry_assistant_messages) == 1
    assert retry_assistant_messages[0]["tool_calls"] == [
        _tool_call("route_banking_service", {"category": "banking", "service": "made-up"})
    ]


def test_classify_retry_also_invalid_falls_back_to_clarification(monkeypatch):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: False)
    _install_post_response_sequence(
        monkeypatch,
        [
            _ollama_response(
                [_tool_call("route_banking_service", {"category": "banking", "service": "made-up"})]
            ),
            _ollama_response(
                [_tool_call("route_banking_service", {"category": "banking", "service": "still-made-up"})]
            ),
        ],
    )

    result = asyncio.run(classify("do the made up thing"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)
    assert not isinstance(result, UnknownService)


def test_classify_retry_produces_no_tool_call_falls_back_to_clarification(monkeypatch):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: False)
    _install_post_response_sequence(
        monkeypatch,
        [
            _ollama_response(
                [_tool_call("route_banking_service", {"category": "banking", "service": "made-up"})]
            ),
            {"message": {}},
        ],
    )

    result = asyncio.run(classify("do the made up thing"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)


def test_classify_retry_produces_ask_clarification_returns_retry_question(monkeypatch):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: False)
    _install_post_response_sequence(
        monkeypatch,
        [
            _ollama_response(
                [_tool_call("route_banking_service", {"category": "banking", "service": "made-up"})]
            ),
            _ollama_response(
                [_tool_call("ask_clarification", {"question": "Which specific thing do you mean?"})]
            ),
        ],
    )

    result = asyncio.run(classify("do the made up thing"))

    assert result == Clarification(question="Which specific thing do you mean?")
    assert result != Clarification(question=_CLARIFICATION_FALLBACK)


# --- classify: T-25 classification model is independent of RAG model -------


def test_classify_request_uses_ollama_classify_model_not_ollama_model(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "some-other-rag-model")
    monkeypatch.setattr(settings, "OLLAMA_CLASSIFY_MODEL", "test-classify-model")
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("answer_kb_question", {})]),
        captured_calls=captured_calls,
    )

    asyncio.run(classify("how does a savings account work?"))

    assert len(captured_calls) == 1
    sent_body = captured_calls[0]["kwargs"]["json"]
    assert sent_body["model"] == "test-classify-model"
    assert sent_body["model"] != "some-other-rag-model"


def test_classify_request_body_sends_configured_think_flag(monkeypatch):
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("answer_kb_question", {})]),
        captured_calls=captured_calls,
    )

    asyncio.run(classify("how does a savings account work?"))

    assert len(captured_calls) == 1
    sent_body = captured_calls[0]["kwargs"]["json"]
    assert sent_body["think"] is settings.OLLAMA_THINK
    assert sent_body["options"]["num_ctx"] == settings.OLLAMA_NUM_CTX


# --- classify: T-40 zero-tool-calls retry -----------------------------------


def test_classify_zero_tool_calls_then_valid_route_on_retry_returns_banking_service(
    monkeypatch,
):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: True)
    captured_calls = []
    _install_post_response_sequence(
        monkeypatch,
        [
            {"message": {}},
            _ollama_response(
                [
                    _tool_call(
                        "route_banking_service",
                        {"category": "banking", "service": "accounts"},
                    )
                ]
            ),
        ],
        captured_calls=captured_calls,
    )

    result = asyncio.run(classify("how much money do I have in my account?"))

    assert result == BankingService(category="banking", service="accounts", subservice=None)
    assert len(captured_calls) == 2

    retry_messages = captured_calls[1]["kwargs"]["json"]["messages"]
    retry_user_texts = [m["content"] for m in retry_messages if m["role"] == "user"]
    assert any("didn't call any tool" in text for text in retry_user_texts)
    # unlike the invalid-path retry, there was no tool call on the first attempt to echo back
    retry_assistant_messages = [m for m in retry_messages if m["role"] == "assistant"]
    assert retry_assistant_messages == []


def test_classify_zero_tool_calls_then_ask_clarification_on_retry(monkeypatch):
    _install_post_response_sequence(
        monkeypatch,
        [
            {"message": {}},
            _ollama_response(
                [_tool_call("ask_clarification", {"question": "What would you like to do?"})]
            ),
        ],
    )

    result = asyncio.run(classify("how much money do I have in my account?"))

    assert result == Clarification(question="What would you like to do?")


def test_classify_zero_tool_calls_then_answer_kb_question_on_retry(monkeypatch):
    _install_post_response_sequence(
        monkeypatch,
        [
            {"message": {}},
            _ollama_response([_tool_call("answer_kb_question", {})]),
        ],
    )

    result = asyncio.run(classify("how much money do I have in my account?"))

    assert result == KbQuestion()


def test_classify_zero_tool_calls_on_both_attempts_falls_back_to_clarification(monkeypatch):
    captured_calls = []
    _install_post_response(monkeypatch, {"message": {}}, captured_calls=captured_calls)

    result = asyncio.run(classify("how much money do I have in my account?"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)
    assert len(captured_calls) == 2


def test_classify_zero_tool_calls_then_invalid_route_on_retry_falls_back_no_third_attempt(
    monkeypatch,
):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: False)
    captured_calls = []
    _install_post_response_sequence(
        monkeypatch,
        [
            {"message": {}},
            _ollama_response(
                [
                    _tool_call(
                        "route_banking_service",
                        {"category": "banking", "service": "made-up-service"},
                    )
                ]
            ),
        ],
        captured_calls=captured_calls,
    )

    result = asyncio.run(classify("how much money do I have in my account?"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)
    assert len(captured_calls) == 2


# --- classify: T-42 crash fix -- missing category/service/question fields --
#
# route_banking_service used to do unguarded arguments["category"] /
# ["service"], and ask_clarification unguarded arguments["question"], in
# three places: the first-attempt handling below, the nested invalid-path
# retry inside it, and T-40's zero-tool-calls retry. A live retry was
# confirmed to omit "category", which raised an unhandled KeyError and
# crashed the /chat SSE stream (500) instead of returning a clarification.
# These tests cover all three call sites for each missing field.


def _spy_is_valid_path(monkeypatch, return_value):
    """Installs a spy for is_valid_path that records every call's arguments
    and returns return_value. Used to confirm the fix's guarantee: a missing
    category/service short-circuits before is_valid_path is ever called with
    a None category or service."""
    calls = []

    def fake(category, service, subservice=None):
        calls.append((category, service, subservice))
        return return_value

    monkeypatch.setattr(routing, "is_valid_path", fake)
    return calls


# Block 1: first-attempt route_banking_service handling


def test_classify_first_attempt_missing_category_returns_clarification_without_crash(
    monkeypatch,
):
    calls = _spy_is_valid_path(monkeypatch, return_value=False)
    _install_post_response_sequence(
        monkeypatch,
        [
            _ollama_response([_tool_call("route_banking_service", {"service": "accounts"})]),
            {"message": {}},
        ],
    )

    result = asyncio.run(classify("missing category on first attempt"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)
    assert all(category is not None for category, service, subservice in calls)


def test_classify_first_attempt_missing_service_returns_clarification_without_crash(
    monkeypatch,
):
    calls = _spy_is_valid_path(monkeypatch, return_value=False)
    _install_post_response_sequence(
        monkeypatch,
        [
            _ollama_response([_tool_call("route_banking_service", {"category": "banking"})]),
            {"message": {}},
        ],
    )

    result = asyncio.run(classify("missing service on first attempt"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)
    assert all(service is not None for category, service, subservice in calls)


def test_classify_first_attempt_missing_question_returns_fallback_clarification(monkeypatch):
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("ask_clarification", {})]),
    )

    result = asyncio.run(classify("vague message"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)


# Block 2: the nested invalid-path retry inside the first-attempt block


def test_classify_invalid_path_retry_missing_category_returns_clarification_without_crash(
    monkeypatch,
):
    calls = _spy_is_valid_path(monkeypatch, return_value=False)
    _install_post_response_sequence(
        monkeypatch,
        [
            _ollama_response(
                [_tool_call("route_banking_service", {"category": "banking", "service": "made-up"})]
            ),
            _ollama_response([_tool_call("route_banking_service", {"service": "accounts"})]),
        ],
    )

    result = asyncio.run(classify("do the made up thing"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)
    assert all(category is not None for category, service, subservice in calls)


def test_classify_invalid_path_retry_missing_service_returns_clarification_without_crash(
    monkeypatch,
):
    calls = _spy_is_valid_path(monkeypatch, return_value=False)
    _install_post_response_sequence(
        monkeypatch,
        [
            _ollama_response(
                [_tool_call("route_banking_service", {"category": "banking", "service": "made-up"})]
            ),
            _ollama_response([_tool_call("route_banking_service", {"category": "banking"})]),
        ],
    )

    result = asyncio.run(classify("do the made up thing"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)
    assert all(service is not None for category, service, subservice in calls)


def test_classify_invalid_path_retry_missing_question_returns_fallback_clarification(
    monkeypatch,
):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: False)
    _install_post_response_sequence(
        monkeypatch,
        [
            _ollama_response(
                [_tool_call("route_banking_service", {"category": "banking", "service": "made-up"})]
            ),
            _ollama_response([_tool_call("ask_clarification", {})]),
        ],
    )

    result = asyncio.run(classify("do the made up thing"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)


# Block 3: T-40's zero-tool-calls retry


def test_classify_zero_tool_calls_retry_missing_category_returns_clarification_without_crash(
    monkeypatch,
):
    calls = _spy_is_valid_path(monkeypatch, return_value=False)
    _install_post_response_sequence(
        monkeypatch,
        [
            {"message": {}},
            _ollama_response([_tool_call("route_banking_service", {"service": "accounts"})]),
        ],
    )

    result = asyncio.run(classify("how much money do I have in my account?"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)
    assert all(category is not None for category, service, subservice in calls)


def test_classify_zero_tool_calls_retry_missing_service_returns_clarification_without_crash(
    monkeypatch,
):
    calls = _spy_is_valid_path(monkeypatch, return_value=False)
    _install_post_response_sequence(
        monkeypatch,
        [
            {"message": {}},
            _ollama_response([_tool_call("route_banking_service", {"category": "banking"})]),
        ],
    )

    result = asyncio.run(classify("how much money do I have in my account?"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)
    assert all(service is not None for category, service, subservice in calls)


def test_classify_zero_tool_calls_retry_missing_question_returns_fallback_clarification(
    monkeypatch,
):
    _install_post_response_sequence(
        monkeypatch,
        [
            {"message": {}},
            _ollama_response([_tool_call("ask_clarification", {})]),
        ],
    )

    result = asyncio.run(classify("how much money do I have in my account?"))

    assert result == Clarification(question=_CLARIFICATION_FALLBACK)


# --- classify: T-47 action-verb + cost-question routes to fees/fee_quote ---
#
# These don't test the model's own judgment (already live-verified 8/8
# separately) -- they test classify()'s handling of the tool call the model
# is now expected to make: category="fees", service="fee_quote" with a
# payload carrying the action's transactionType/amount, for a message that
# combines an action verb with a cost question.


def test_classify_action_plus_cost_question_returns_fee_quote_banking_service(monkeypatch):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: True)
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [
                _tool_call(
                    "route_banking_service",
                    {
                        "category": "fees",
                        "service": "fee_quote",
                        "payload": {"transactionType": "bkash", "amount": 1000},
                    },
                )
            ]
        ),
    )

    result = asyncio.run(
        classify("If i transfer 1000 from my account to bkash what is the fee?")
    )

    assert result == BankingService(
        category="fees",
        service="fee_quote",
        subservice=None,
        payload={"transactionType": "bkash", "amount": 1000},
    )
    # must NOT have been misrouted to the action's own category (e.g. transfers)
    assert result.category != "polygon_services"


def test_classify_withdraw_plus_cost_question_returns_fee_quote_banking_service(monkeypatch):
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: True)
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [
                _tool_call(
                    "route_banking_service",
                    {
                        "category": "fees",
                        "service": "fee_quote",
                        "payload": {"transactionType": "atm_withdrawal", "amount": 2000},
                    },
                )
            ]
        ),
    )

    result = asyncio.run(classify("what will I be charged if I withdraw 2000 from an ATM?"))

    assert result == BankingService(
        category="fees",
        service="fee_quote",
        subservice=None,
        payload={"transactionType": "atm_withdrawal", "amount": 2000},
    )


# --- _coerce_payload (T-48) --------------------------------------------------
#
# Ollama tool-calling (observed with qwen3:8b) can return `payload` as a
# JSON-encoded string instead of a real nested object, which used to crash
# downstream adapters with `AttributeError: 'str' object has no attribute
# 'get'`. These lock in _coerce_payload's contract in isolation: dicts pass
# through unchanged, JSON-object strings parse to dicts, and everything else
# (non-dict JSON, malformed JSON, other types) collapses to None instead of
# raising.


def test_coerce_payload_dict_passthrough_unchanged():
    payload = {"transactionType": "bkash", "amount": 1000}

    assert _coerce_payload(payload) == payload  # equal copy (empty values are dropped)


def test_coerce_payload_json_object_string_parses_to_dict():
    result = _coerce_payload('{"transactionType": "bkash", "amount": 1000}')

    assert result == {"transactionType": "bkash", "amount": 1000}


def test_coerce_payload_json_array_string_returns_none():
    assert _coerce_payload("[1, 2, 3]") is None


def test_coerce_payload_json_scalar_string_returns_none():
    # a JSON string that parses to a JSON string (i.e. a quoted string)
    assert _coerce_payload('"just a string"') is None


def test_coerce_payload_json_number_string_returns_none():
    assert _coerce_payload("42") is None


def test_coerce_payload_malformed_json_string_returns_none_not_raises():
    # unterminated object -- must not raise, just collapse to None
    assert _coerce_payload('{"transactionType": "bkash"') is None


def test_coerce_payload_none_returns_none():
    assert _coerce_payload(None) is None


def test_coerce_payload_int_returns_none():
    assert _coerce_payload(42) is None


def test_coerce_payload_list_returns_none():
    assert _coerce_payload([{"transactionType": "bkash"}]) is None


# --- classify: T-48 payload-as-JSON-string crash fix -------------------------


def test_classify_route_banking_service_coerces_json_string_payload_to_dict(monkeypatch):
    # Reproduces the live crash: Ollama's tool call returned `payload` as a
    # JSON-encoded string rather than a nested object, which used to flow
    # straight into BankingService.payload and later blow up in
    # app/banking/adapters/real.py with `AttributeError: 'str' object has no
    # attribute 'get'`. classify() must now coerce it to a real dict end to
    # end, with no crash.
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: True)
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [
                _tool_call(
                    "route_banking_service",
                    {
                        "category": "fees",
                        "service": "fee_quote",
                        "payload": '{"transactionType": "bkash", "amount": 1000}',
                    },
                )
            ]
        ),
    )

    result = asyncio.run(classify("how much does it cost to send money via bKash"))

    assert result == BankingService(
        category="fees",
        service="fee_quote",
        subservice=None,
        payload={"transactionType": "bkash", "amount": 1000},
    )
    assert isinstance(result.payload, dict)


# --- build_system_prompt: T-50 fees-are-never-a-KB-topic exception ----------
#
# Rule 1 now carves out an exception -- any message clearly asking about fees,
# even informationally-phrased ones, must never resolve to answer_kb_question.
# These lock in the exception clause and its new few-shot example verbatim so
# a future prompt edit can't silently drop or reword them.






# --- build_system_prompt: T-58 four new few-shot example blocks ------------
#
# The implementing agent live-verified these against a real model but, per
# the pre-existing pattern noted for T-56 above, added no prompt-content
# regression assertions -- these lock in the exact wording so a future prompt
# edit can't silently drop or reword any of them.












def test_classify_informational_fees_question_returns_clarification_not_kb_question(monkeypatch):
    # T-50: "what do you know about fees?" is phrased like a KB question, but
    # per the new rule-1 exception the model must call ask_clarification
    # (since neither transaction type nor amount is known), never
    # answer_kb_question.
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [
                _tool_call(
                    "ask_clarification",
                    {
                        "question": (
                            "Sure — which transaction type would you like a fee quote for, and "
                            "for what amount? For example, a bank transfer, bKash, or another "
                            "wallet?"
                        )
                    },
                )
            ]
        ),
    )

    result = asyncio.run(classify("what do you know about fees?"))

    assert result == Clarification(
        question=(
            "Sure — which transaction type would you like a fee quote for, and for what "
            "amount? For example, a bank transfer, bKash, or another wallet?"
        )
    )
    assert not isinstance(result, KbQuestion)


# --- classify: T-59 ACCOUNT_SELECTION_REQUIRED gets its own dedicated context note,
# distinct from the generic CLARIFICATION_REQUIRED branch above ------------------
#
# Live-reproduced regression: an unrelated message sent right after an
# ACCOUNT_SELECTION_REQUIRED pending turn (e.g. "how many accounts do i have?"
# answering nothing, just a fresh request) was getting hijacked into a transfer
# clarification -- the generic branch's context note didn't say what KIND of
# pending state this was, so the new message's surface wording ("accounts")
# collided with the Transfer-specific rule's own "raw account number" examples.
# These tests lock in the dedicated branch: it must name the already-known
# category/service, explicitly rule out transfer/wallet/beneficiary
# reinterpretation, and never fall back to the fee-quote-specific wording.


def _account_selection_turn(message="what's my balance?", subservice=None):
    classification = {
        "type": "ACCOUNT_SELECTION_REQUIRED",
        "category": "account_info",
        "service": "balance",
        "subservice": subservice,
        "question": (
            "You have multiple accounts — which one did you mean? Savings account ending "
            "0015, Credit account ending 0379."
        ),
    }
    return ChatTurn(timestamp=datetime.now(timezone.utc), message=message, classification=classification)


def test_classify_account_selection_required_uses_dedicated_context_note(monkeypatch):
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("answer_kb_question", {})]),
        captured_calls=captured_calls,
    )

    asyncio.run(
        classify("how many accounts do i have?", recent_turns=[_account_selection_turn()])
    )

    system_texts = [
        m["content"]
        for m in captured_calls[0]["kwargs"]["json"]["messages"]
        if m["role"] == "system"
    ]
    assert any("PENDING ACCOUNT SELECTION" in text for text in system_texts)
    # never the generic "PENDING CLARIFICATION" branch's narrative wording
    assert not any("PENDING CLARIFICATION" in text for text in system_texts)


def test_classify_account_selection_required_context_names_already_known_service(monkeypatch):
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("answer_kb_question", {})]),
        captured_calls=captured_calls,
    )

    asyncio.run(
        classify("how many accounts do i have?", recent_turns=[_account_selection_turn()])
    )

    system_texts = [
        m["content"]
        for m in captured_calls[0]["kwargs"]["json"]["messages"]
        if m["role"] == "system"
    ]
    assert any(
        'with EXACTLY category="account_info", service="balance"' in text
        for text in system_texts
    )


def test_classify_account_selection_required_context_rules_out_transfer_reinterpretation(
    monkeypatch,
):
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("answer_kb_question", {})]),
        captured_calls=captured_calls,
    )

    asyncio.run(
        classify("how many accounts do i have?", recent_turns=[_account_selection_turn()])
    )

    system_texts = [
        m["content"]
        for m in captured_calls[0]["kwargs"]["json"]["messages"]
        if m["role"] == "system"
    ]
    assert any(
        "has NOTHING to do with a transfer destination, a wallet, a beneficiary, or "
        "sending money anywhere" in text
        for text in system_texts
    )
    assert any(
        'how many accounts do i have?" -> does not name any of the specific listed accounts'
        in text
        for text in system_texts
    )


def test_classify_account_selection_required_context_includes_subservice_when_present(
    monkeypatch,
):
    captured_calls = []
    _install_post_response(
        monkeypatch,
        _ollama_response([_tool_call("answer_kb_question", {})]),
        captured_calls=captured_calls,
    )

    asyncio.run(
        classify(
            "savings",
            recent_turns=[_account_selection_turn(subservice="some_subservice")],
        )
    )

    system_texts = [
        m["content"]
        for m in captured_calls[0]["kwargs"]["json"]["messages"]
        if m["role"] == "system"
    ]
    assert any(
        'category="account_info", service="balance", subservice="some_subservice"' in text
        for text in system_texts
    )


def test_classify_account_selection_required_unrelated_message_resolves_independently(
    monkeypatch,
):
    # Simulates the model correctly following the dedicated context note: an
    # unrelated new message resolves to its own, different category/service,
    # never to the pending balance selection nor to a transfer.
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: True)
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [_tool_call("route_banking_service", {"category": "banking", "service": "accounts"})]
        ),
    )

    result = asyncio.run(
        classify("how many accounts do i have?", recent_turns=[_account_selection_turn()])
    )

    assert result == BankingService(category="banking", service="accounts", subservice=None)
    assert result.category != "transfer"


def test_classify_account_selection_required_genuine_answer_resolves_to_same_service(
    monkeypatch,
):
    # Simulates the model correctly following the dedicated context note: a
    # message naming one of the listed accounts by type resolves back to the
    # SAME already-identified category/service.
    monkeypatch.setattr(routing, "is_valid_path", lambda *a, **k: True)
    _install_post_response(
        monkeypatch,
        _ollama_response(
            [
                _tool_call(
                    "route_banking_service",
                    {
                        "category": "account_info",
                        "service": "balance",
                        "payload": {"accountType": "savings"},
                    },
                )
            ]
        ),
    )

    result = asyncio.run(classify("savings", recent_turns=[_account_selection_turn()]))

    assert result == BankingService(
        category="account_info",
        service="balance",
        subservice=None,
        payload={"accountType": "savings"},
    )
