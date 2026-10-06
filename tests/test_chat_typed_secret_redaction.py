"""A code/password typed into the chat box must never be kept (T-77 follow-up).

At ANY step -- a pending yes/no, a pending verification, or a fresh message -- text
shaped like a code is stored in the session turn and written to the request log as the
placeholder, never as typed; so it can't come back later through the composer's
conversation history. Structured payload secrets (otp/pin/password) are never logged or
stored either. Normal messages are stored verbatim. Real in-memory session store, every
bank call mocked at its app.routes.chat import site; nothing reaches a network.
"""
import json
import logging

import pytest

import app.banking.session as session_module
import app.routes.chat as chat_module
from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, Clarification

from tests.conftest import AUTH_HEADERS

PHONE = "01712345678"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}
CODE = "482916"
PLACEHOLDER = chat_module._REDACTED_SUBMISSION

FREEZE = BankingService("card_services", "frezz_unfrezz", None,
                        {"cardId": "41", "cardLast4": "0251", "reason": "lost"})
NICKNAME = BankingService("profile_update", "update_nickname", None, {"nickName": "Rafi"})
BENEFICIARY = BankingService("beneficiary_management", "beneficiary_add", None,
                             {"nickname": "Rahim", "accountNumber": "1234567890", "serviceType": "OTHER_BANK",
                              "bankName": "B", "branchName": "Br", "routingNumber": "0123"})


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(session_module, "_sessions", {})
    state = {"fulfills": [], "sends": [], "classified": []}

    async def verify_jwt(token):
        return CustomerIdentity(customer_id=PHONE)

    async def classify(message, recent_turns=None):
        state["classified"].append(message)
        lowered = message.lower()
        if "freeze" in lowered:
            return FREEZE
        if "nickname" in lowered:
            return NICKNAME
        if "beneficiary" in lowered:
            return BENEFICIARY
        return Clarification(question="What would you like to do?")

    async def send_otp(phone):
        state["sends"].append(phone)

    async def fulfill(customer_identity, jwt, category, service, subservice, payload):
        state["fulfills"].append((category, service))
        return AdapterResult(data={"success": True})

    async def lookup_recipient(token, account):
        return None

    monkeypatch.setattr(chat_module, "verify_jwt", verify_jwt)
    monkeypatch.setattr(chat_module, "classify", classify)
    monkeypatch.setattr(chat_module, "send_otp", send_otp)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fulfill)
    monkeypatch.setattr(chat_module, "lookup_recipient", lookup_recipient)
    return state


def _post(client, message, payload=None):
    body = {"message": message}
    if payload is not None:
        body["payload"] = payload
    resp = client.post("/chat", json=body, headers=JWT_HEADERS)
    assert resp.status_code == 200
    return resp.text


def _turns():
    return session_module.get_session(PHONE)


def _logs(caplog):
    return "\n".join(f"{r.name} {r.getMessage()}" for r in caplog.records)


def _assert_code_nowhere(caplog, secret=CODE):
    assert secret not in _logs(caplog), "secret leaked into a log line"
    assert secret not in repr(_turns()), "secret leaked into the stored session"
    assert secret not in json.dumps(chat_module._history(_turns())), "secret would reach the composer"


def _request_log_messages(caplog):
    """The `message` field of every request-entry log line."""
    out = []
    for record in caplog.records:
        text = record.getMessage()
        if text.startswith("{") and '"auth_present"' in text:
            out.append(json.loads(text)["message"])
    return out


@pytest.mark.parametrize("starter", [
    "please freeze my card",
    "change my nickname to Rafi",
    "add a beneficiary",
])
def test_code_typed_at_a_pending_yes_no_is_stored_and_logged_as_the_placeholder(
        client, env, caplog, starter):
    caplog.set_level(logging.DEBUG)
    first = _post(client, starter)
    assert "CONFIRMATION_REQUIRED" in first
    _post(client, f"my code is {CODE}")

    assert _turns()[-1].message == PLACEHOLDER
    assert _request_log_messages(caplog)[-1] == PLACEHOLDER
    _assert_code_nowhere(caplog)
    # nothing ran on it: no classify, no send, no bank call
    assert env["classified"] == [starter]
    assert env["sends"] == [] and env["fulfills"] == []
    # the very next turn's history carries the earlier question but not the code
    history = chat_module._history(_turns())
    assert ("Customer", starter) in history
    assert all(CODE not in said for _, said in history)


def test_bare_code_at_a_yes_no_is_also_redacted(client, env, caplog):
    caplog.set_level(logging.DEBUG)
    _post(client, "change my nickname to Rafi")
    _post(client, CODE)
    assert _turns()[-1].message == PLACEHOLDER
    _assert_code_nowhere(caplog)


def test_code_shaped_fresh_message_is_stored_and_logged_as_the_placeholder(client, env, caplog):
    caplog.set_level(logging.DEBUG)
    _post(client, f"{CODE}")
    assert _turns()[-1].message == PLACEHOLDER
    assert _request_log_messages(caplog) == [PLACEHOLDER]
    _assert_code_nowhere(caplog)


def test_code_typed_at_a_pending_verification_step_is_redacted_as_before(client, env, caplog):
    caplog.set_level(logging.DEBUG)
    _post(client, "please freeze my card")
    _post(client, "Confirm", {"confirm": True})  # -> OTP step
    assert env["sends"] == [PHONE]
    _post(client, f"the code is {CODE}")
    assert all(turn.message != f"the code is {CODE}" for turn in _turns())
    _assert_code_nowhere(caplog)
    assert env["fulfills"] == []


def test_a_normal_message_is_stored_and_logged_verbatim(client, env, caplog):
    caplog.set_level(logging.DEBUG)
    _post(client, "freeze my card")
    assert _turns()[-1].message == "freeze my card"
    assert _request_log_messages(caplog) == ["freeze my card"]
    assert ("Customer", "freeze my card") in chat_module._history(_turns())


@pytest.mark.parametrize("message", ["what is my balance", "send 500 to bkash", "i have 2 cards", "ok"])
def test_ordinary_messages_including_short_numbers_are_not_redacted(client, env, caplog, message):
    _post(client, message)
    assert _turns()[-1].message == message


def test_payload_secrets_never_reach_the_log_or_the_stored_turn(client, env, caplog):
    caplog.set_level(logging.DEBUG)
    _post(client, "please freeze my card")
    _post(client, "Confirm", {"confirm": True})
    _post(client, "submit", {"otp": "731942", "pin": "864209"})
    _post(client, "hello", {"password": "Zq7!HorseBattery", "otp": "555123"})
    for secret in ("731942", "864209", "Zq7!HorseBattery", "555123"):
        assert secret not in _logs(caplog), secret
        assert secret not in repr(_turns()), secret
    # every turn that carried a submission is the placeholder, never the typed text
    assert _turns()[-1].message == PLACEHOLDER
    for turn in _turns():
        assert not {"pin", "password", "otp"} & set((turn.classification or {}).get("payload") or {})


def test_message_with_a_secret_payload_is_redacted_even_if_the_text_looks_ordinary(client, env, caplog):
    caplog.set_level(logging.DEBUG)
    _post(client, "here you go", {"pin": "864209"})
    assert _turns()[-1].message == PLACEHOLDER
    assert _request_log_messages(caplog)[-1] == PLACEHOLDER
    assert "864209" not in _logs(caplog) and "864209" not in repr(_turns())


def test_kb_question_turn_is_stored_verbatim_and_a_coded_one_redacted(client, env, caplog, monkeypatch):
    from app.banking.routing import KbQuestion

    async def classify(message, recent_turns=None):
        return KbQuestion()

    async def embed(message, client=None):
        return [0.1] * 384

    async def stream(prompt):
        yield "ok"

    monkeypatch.setattr(chat_module, "classify", classify)
    monkeypatch.setattr(chat_module, "embed_text", embed)
    monkeypatch.setattr(chat_module, "search", lambda v, k: [])
    monkeypatch.setattr(chat_module, "stream_generate", stream)
    caplog.set_level(logging.DEBUG)
    _post(client, "what is a DPS")
    assert _turns()[-1].message == "what is a DPS"
    _post(client, f"what is a DPS 2 {CODE}")
    assert _turns()[-1].message == PLACEHOLDER
    assert CODE not in repr(_turns())
