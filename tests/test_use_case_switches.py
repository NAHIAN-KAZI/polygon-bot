"""A use case the bank switched off in the back office is not done in chat (T-109)."""
import json
from datetime import datetime, timezone

import app.routes.chat as chat_module
from app.banking import session as session_module
from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService
from app.banking.session import ChatTurn

from tests.conftest import AUTH_HEADERS

CUSTOMER = "cust-switch"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}
FREEZE = "card_services.frezz_unfrezz"
BALANCE = "account_info.balance"


def _parse_sse(body):
    out = []
    for block in body.strip("\n").split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            out.append((name, data))
    return out


def _wire(monkeypatch, routed, calls):
    async def fake_classify(message, recent_turns=None, app_notes=None):
        return routed

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        calls.append((category, service))
        return AdapterResult(data={"balance": "500.00", "cards": []})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module.audit, "log_banking_turn", lambda *a, **k: None)
    monkeypatch.setattr(chat_module, "is_valid_path", lambda *a, **k: True)


def _post(client, body):
    resp = client.post("/chat", json=body, headers=JWT_HEADERS)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    reply = "".join(d.get("token", "") for n, d in events if n == "token")
    result = next((d for n, d in events if n == "result"), {})
    return reply, result


def test_a_switched_off_use_case_with_an_app_screen_offers_the_screen_and_calls_no_bank(client, monkeypatch):
    session_module._sessions.clear()
    calls = []
    _wire(monkeypatch, BankingService("card_services", "frezz_unfrezz", None, {"reason": "stolen"}), calls)
    try:
        reply, result = _post(client, {"message": "freeze my card", "disabled_use_cases": [FREEZE]})
    finally:
        session_module._sessions.clear()
    assert calls == []
    assert result["type"] == "APP_ACTION"
    assert result["payload"]["useCaseDisabled"] is True and result["payload"]["useCase"] == FREEZE
    assert result["payload"]["ui"]["route"] == "/freeze_card" and result["payload"]["executed"] is False
    assert reply.startswith("switched_off") and "Freeze a card" in reply and "Freeze or unfreeze card" in reply
    assert result["payload"]["ui"]["title"] == "Freeze or unfreeze card"


def test_a_switched_off_use_case_without_a_screen_is_a_plain_notice(client, monkeypatch):
    session_module._sessions.clear()
    calls = []
    _wire(monkeypatch, BankingService("account_info", "balance", None, None), calls)
    try:
        reply, result = _post(client, {"message": "what's my balance", "disabled_use_cases": [BALANCE]})
    finally:
        session_module._sessions.clear()
    assert calls == []
    assert result["type"] == "USE_CASE_DISABLED"
    assert result["payload"] == {"useCase": BALANCE, "useCaseDisabled": True}
    assert reply.startswith("switched_off") and "where" not in reply


def test_nothing_changes_when_no_use_case_is_off_or_a_different_one_is(client, monkeypatch):
    for disabled in ([], [FREEZE]):
        session_module._sessions.clear()
        calls = []
        _wire(monkeypatch, BankingService("account_info", "balance", None, None), calls)
        try:
            _reply, result = _post(client, {"message": "what's my balance", "disabled_use_cases": disabled})
        finally:
            session_module._sessions.clear()
        assert calls == [("account_info", "balance")]
        assert result["type"] == "BANKING_SERVICE"


def test_a_direct_route_request_is_blocked_too(client, monkeypatch):
    session_module._sessions.clear()
    calls = []
    _wire(monkeypatch, BankingService("account_info", "balance", None, None), calls)
    try:
        _reply, result = _post(client, {"message": "show", "category": "account_info", "service": "balance",
                                        "disabled_use_cases": [BALANCE]})
    finally:
        session_module._sessions.clear()
    assert calls == [] and result["type"] == "USE_CASE_DISABLED"


def test_an_app_action_can_be_switched_off(client, monkeypatch):
    session_module._sessions.clear()
    calls = []
    _wire(monkeypatch, BankingService("app_actions", "card_close", None, None), calls)
    try:
        _reply, result = _post(client, {"message": "close my card", "disabled_use_cases": ["app_actions.card_close"]})
    finally:
        session_module._sessions.clear()
    assert result["type"] == "APP_ACTION" and result["payload"]["useCaseDisabled"] is True
    assert result["service"] == "card_close"


def test_a_pending_confirmation_is_not_executed_once_the_use_case_is_off(client, monkeypatch):
    session_module._sessions.clear()
    calls = []
    _wire(monkeypatch, BankingService("account_info", "balance", None, None), calls)

    async def reads_yes(question, message, payload):
        return "confirm"

    monkeypatch.setattr(chat_module, "_read_pending_reply", reads_yes)
    session_module.record_turn(CUSTOMER, ChatTurn(
        timestamp=datetime.now(timezone.utc), message="change my nickname to Rafi",
        classification={"type": "CONFIRMATION_REQUIRED", "category": "profile_update", "service": "update_nickname",
                        "subservice": None, "payload": {"nickname": "Rafi"}, "question": "Change it to Rafi?"}))
    try:
        _reply, result = _post(client, {"message": "yes", "disabled_use_cases": ["profile_update.update_nickname"]})
    finally:
        session_module._sessions.clear()
    assert calls == [] and result["type"] == "USE_CASE_DISABLED"


def test_a_pending_verification_step_ends_when_the_use_case_is_off(client, monkeypatch):
    session_module._sessions.clear()
    calls = []
    _wire(monkeypatch, BankingService("account_info", "balance", None, None), calls)

    async def must_not_run(*a, **k):
        raise AssertionError("the verification handler must not run for a switched-off use case")

    monkeypatch.setattr(chat_module, "_handle_freeze_otp_reply", must_not_run)

    async def reads_other(question, message, payload):
        return "answer"

    monkeypatch.setattr(chat_module, "_read_pending_reply", reads_other)
    session_module.record_turn(CUSTOMER, ChatTurn(
        timestamp=datetime.now(timezone.utc), message="freeze it",
        classification={"type": chat_module._OTP_PENDING_TYPE, "category": "card_services", "service": "frezz_unfrezz",
                        "subservice": None, "payload": {"cardId": "c1"}, "question": "Enter the code"}))
    try:
        _reply, result = _post(client, {"message": "123456", "disabled_use_cases": [FREEZE]})
    finally:
        session_module._sessions.clear()
    assert result["type"] == "APP_ACTION" and result["payload"]["useCaseDisabled"] is True


def test_the_request_accepts_the_field_and_defaults_to_empty():
    assert chat_module.ChatRequest(message="hi").disabled_use_cases == []
    assert chat_module.ChatRequest(message="hi", disabled_use_cases=["a.b"]).disabled_use_cases == ["a.b"]
