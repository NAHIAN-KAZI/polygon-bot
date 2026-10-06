"""T-57: card-freeze OTP + PIN/password step-up in app/routes/chat.py.

Every OTP send/verify and freeze call is mocked at its app.routes.chat import site
(send_otp / verify_otp / fulfill_banking_service) -- nothing here ever reaches the
live OTP or freeze endpoints. Uses the REAL in-memory session store (reset per
test) so the pending OTP_REQUIRED state carries across turns exactly as in
production, and so persisted session state can be inspected for secrets.
"""
import json
import logging

import pytest

import app.banking.session as session_module
import app.routes.chat as chat_module
from app.banking.adapters.base import (
    AdapterResult,
    AdapterUnavailableError,
    AdapterValidationError,
)
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, Clarification

from tests.conftest import AUTH_HEADERS

CUSTOMER_PHONE = "01712345678"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}
CARD_PAYLOAD = {"cardId": "41", "cardLast4": "0251", "reason": "lost"}


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip("\n").split("\n\n"):
        if not block.strip():
            continue
        event_name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((event_name, data))
    return events


def _result(events):
    return next(data for name, data in events if name == "result")


def _token(events):
    return "".join(data["token"] for name, data in events if name == "token")


class FakeBank:
    """Records every OTP/freeze call; behaviour scripted per test."""

    def __init__(self):
        self.sends: list[str] = []
        self.verifies: list[tuple[str, str]] = []
        self.freezes: list[dict] = []
        self.verify_errors: list[Exception] = []
        self.freeze_errors: list[Exception] = []
        self.send_errors: list[Exception] = []
        self.token_counter = 0

    async def send_otp(self, phone):
        self.sends.append(phone)
        if self.send_errors:
            raise self.send_errors.pop(0)

    async def verify_otp(self, phone, otp):
        self.verifies.append((phone, otp))
        if self.verify_errors:
            raise self.verify_errors.pop(0)
        self.token_counter += 1
        return f"vtoken-{self.token_counter}"

    async def fulfill(self, customer_identity, jwt, category, service, subservice, payload):
        assert (category, service) == ("card_services", "frezz_unfrezz")
        self.freezes.append(dict(payload))
        if self.freeze_errors:
            raise self.freeze_errors.pop(0)
        return AdapterResult(data={"data": {"id": "41", "status": "BLOCKED", "cardNumber": "4001230000000251", "cifNumber": "109260000202", "phone": "01311111110"}})


@pytest.fixture
def bank(monkeypatch):
    monkeypatch.setattr(session_module, "_sessions", {})
    fake = FakeBank()

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_PHONE)

    classify_calls = []

    async def fake_classify(message, recent_turns=None):
        classify_calls.append(message)
        if "freeze" in message.lower():
            return BankingService(
                category="card_services", service="frezz_unfrezz", subservice=None,
                payload=dict(CARD_PAYLOAD),
            )
        return Clarification(question="What would you like to do?")

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "send_otp", fake.send_otp)
    monkeypatch.setattr(chat_module, "verify_otp", fake.verify_otp)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake.fulfill)
    fake.classify_calls = classify_calls
    return fake


def _post(client, message, payload=None, **extra):
    body = {"message": message, **extra}
    if payload is not None:
        body["payload"] = payload
    resp = client.post("/chat", json=body, headers=JWT_HEADERS)
    assert resp.status_code == 200
    return _parse_sse(resp.text)


def _ask_freeze(client, bank):
    """The freeze request: ends in a yes/no, and NO verification code is sent yet."""
    events = _post(client, "please freeze my card")
    assert _result(events)["type"] == "CONFIRMATION_REQUIRED"
    assert bank.sends == []
    return events


def _start(client, bank):
    """Request -> yes/no -> (the customer taps Confirm) -> code sent, OTP step pending."""
    _ask_freeze(client, bank)
    events = _post(client, "Confirm", {"confirm": True})
    assert _result(events)["type"] == "OTP_REQUIRED"
    assert bank.sends == [CUSTOMER_PHONE]
    return events


# --- happy paths --------------------------------------------------------------


def test_otp_and_pin_freezes_card(client, bank):
    _start(client, bank)
    events = _post(client, "submit", {"otp": "0000", "pin": "123456"})

    assert bank.verifies == [(CUSTOMER_PHONE, "0000")]
    assert len(bank.freezes) == 1
    sent = bank.freezes[0]
    assert sent["verificationToken"] == "vtoken-1"
    assert sent["pin"] == "123456"
    assert "password" not in sent
    assert sent["cardId"] == "41"

    token = _token(events)
    assert token.startswith("done:")
    assert "what: the card was frozen" in token
    assert "card ending: 0251" in token
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE"
    # Only the outcome reaches the frontend -- never the bank's raw card record.
    assert result["payload"] == {"executed": True, "cardId": "41", "cardLast4": "0251", "status": "BLOCKED"}
    assert result["routing"]["action"] == "redirect"
    # Flow is over: the next message is a fresh classification.
    _post(client, "hello there")
    assert bank.classify_calls[-1] == "hello there"


def test_otp_and_password_freezes_card(client, bank):
    _start(client, bank)
    _post(client, "submit", {"otp": "0000", "password": "Secret@1"})
    assert bank.freezes[0]["password"] == "Secret@1"
    assert "pin" not in bank.freezes[0]


def test_explicit_resubmit_of_same_service_with_otp_is_treated_as_the_otp_reply(client, bank):
    _start(client, bank)
    events = _post(
        client, "submit", {"otp": "0000", "pin": "123456"},
        category="card_services", service="frezz_unfrezz",
    )
    assert _result(events)["type"] == "BANKING_SERVICE"
    assert len(bank.sends) == 1  # no second OTP send
    assert len(bank.freezes) == 1


# --- credential-shape validation (never reaches verify/freeze) ---------------


def test_both_pin_and_password_reasks(client, bank):
    _start(client, bank)
    events = _post(client, "submit", {"otp": "0000", "pin": "123456", "password": "pw"})
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["verificationStatus"] == "CREDENTIALS_INVALID_COMBINATION"
    assert _token(events).startswith("verify:")
    assert "only one of them is needed" in _token(events)
    assert bank.verifies == [] and bank.freezes == []


def test_otp_without_pin_or_password_reasks(client, bank):
    _start(client, bank)
    events = _post(client, "submit", {"otp": "0000"})
    assert _result(events)["payload"]["verificationStatus"] == "CREDENTIALS_MISSING"
    assert bank.verifies == [] and bank.freezes == []


def test_otp_typed_in_message_text_is_never_parsed(client, bank):
    _start(client, bank)
    events = _post(client, "my code is 0000 and pin 123456")
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["verificationStatus"] == "CREDENTIALS_MISSING"
    assert bank.verifies == [] and bank.freezes == []
    # And it never went to the LLM classifier either.
    assert bank.classify_calls == ["please freeze my card"]


# --- the yes/no BEFORE any code is sent (live QA: "Withdraw cash" was routed to a
# --- freeze and an SMS went out the customer never asked for) ---------------------


def test_freeze_request_asks_yes_no_and_sends_no_code(client, bank):
    events = _ask_freeze(client, bank)
    result = _result(events)
    assert result["category"] == "card_services" and result["service"] == "frezz_unfrezz"
    # the exact card and the reason travel with it; secrets never do
    assert result["payload"] == CARD_PAYLOAD
    token = _token(events)
    assert token.startswith("confirm:")
    assert "card ending: 0251" in token
    assert "their reason: lost" in token
    assert "to confirm: say yes" in token and "to cancel: say no" in token
    assert "verification code is sent to their phone" in token
    assert bank.sends == [] and bank.verifies == [] and bank.freezes == []
    pending = session_module.get_session(CUSTOMER_PHONE)[-1].classification
    assert pending["type"] == "CONFIRMATION_REQUIRED"
    assert (pending["category"], pending["service"]) == ("card_services", "frezz_unfrezz")
    assert pending["payload"] == CARD_PAYLOAD
    assert pending["question"] == token


def test_confirm_button_sends_the_code_once_to_the_jwt_customers_phone(client, bank):
    _ask_freeze(client, bank)
    events = _post(client, "Confirm", {"confirm": True})
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["verificationStatus"] == "OTP_SENT"
    assert result["payload"]["cardLast4"] == "0251"
    assert _token(events).startswith("verify:")
    assert bank.sends == [CUSTOMER_PHONE]
    assert bank.verifies == [] and bank.freezes == []
    assert bank.classify_calls == ["please freeze my card"]


def test_typed_yes_sends_the_code_but_never_freezes(client, bank):
    _ask_freeze(client, bank)
    events = _post(client, "yes")
    assert _result(events)["type"] == "OTP_REQUIRED"
    assert bank.sends == [CUSTOMER_PHONE]
    assert bank.freezes == []
    assert bank.classify_calls == ["please freeze my card"]


@pytest.mark.parametrize("reply,payload", [("no", None), ("Cancel", {"confirm": False})])
def test_declining_the_yes_no_sends_nothing_and_calls_no_bank(client, bank, reply, payload):
    _ask_freeze(client, bank)
    events = _post(client, reply, payload)
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE"
    assert result["payload"] == {"executed": False, "cancelled": True}
    assert _token(events).startswith("declined:")
    assert bank.sends == [] and bank.verifies == [] and bank.freezes == []
    # Flow is over: a later "yes" revives nothing.
    _post(client, "yes")
    assert bank.sends == [] and bank.freezes == []


def test_unclear_reply_reasks_the_yes_no_and_sends_nothing(client, bank):
    first = _ask_freeze(client, bank)
    events = _post(client, "hmm")
    assert _result(events)["type"] == "CONFIRMATION_REQUIRED"
    assert _token(events) == _token(first)
    assert bank.sends == [] and bank.freezes == []
    assert bank.classify_calls == ["please freeze my card"]
    # still pending: a yes now sends the code
    assert _result(_post(client, "yes"))["type"] == "OTP_REQUIRED"
    assert bank.sends == [CUSTOMER_PHONE]


def test_a_different_request_drops_the_freeze_and_sends_no_code(client, bank):
    _ask_freeze(client, bank)
    events = _post(client, "what is my account balance please")
    assert bank.classify_calls == ["please freeze my card", "what is my account balance please"]
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"  # the classifier's answer
    assert bank.sends == [] and bank.freezes == []
    _post(client, "yes")
    assert bank.sends == []


def test_code_typed_at_the_freeze_yes_no_never_executes_or_classifies(client, bank, monkeypatch):
    import httpx

    async def never(self, *a, **k):
        raise AssertionError("a typed secret must never reach a model")

    _ask_freeze(client, bank)
    monkeypatch.setattr(httpx.AsyncClient, "post", never)
    events = _post(client, "my code is 482916")
    assert _result(events)["type"] == "CONFIRMATION_REQUIRED"  # asked again, nothing runs
    assert bank.sends == [] and bank.verifies == [] and bank.freezes == []
    assert bank.classify_calls == ["please freeze my card"]


def test_explicit_freeze_request_with_a_reason_still_gets_a_yes_no_never_an_otp(client, bank, monkeypatch):
    # The app resubmits category+service+payload directly (no classifier involved).
    monkeypatch.setattr(chat_module, "is_valid_path", lambda c, s, sub=None: True)
    events = _post(client, "freeze it", dict(CARD_PAYLOAD), category="card_services", service="frezz_unfrezz")
    assert _result(events)["type"] == "CONFIRMATION_REQUIRED"
    assert bank.sends == []


def test_a_classifier_invented_block_request_still_ends_in_a_yes_no(client, bank, monkeypatch):
    """Live: the model copied one quote ("Withdraw cash") into both `reason` and
    `block_request`, so the grounding check passed. Whatever the classifier and the
    grounding say, a freeze only ever reaches a yes/no -- never a code."""


    async def grounded_by_copy(result, message, recent_turns):
        # the 8B's behaviour: same quote for reason and block_request -> freeze kept
        payload = dict(result.payload or {})
        payload["reason"] = message
        return BankingService(result.category, result.service, result.subservice, payload)

    async def fake_classify(message, recent_turns=None):
        bank.classify_calls.append(message)
        return BankingService("card_services", "frezz_unfrezz", None, {"cardId": "41", "cardLast4": "0251"})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "_ground_freeze_request", grounded_by_copy)
    events = _post(client, "Withdraw cash")
    assert _result(events)["type"] == "CONFIRMATION_REQUIRED"
    assert "their reason: Withdraw cash" in _token(events)  # the customer can see it and say no
    assert bank.sends == [] and bank.freezes == []
    declined = _post(client, "no")
    assert _result(declined)["payload"] == {"executed": False, "cancelled": True}
    assert bank.sends == []


def test_cancel_while_pending_stops_without_freezing(client, bank):
    _start(client, bank)
    events = _post(client, "cancel")
    assert _token(events).startswith("declined:")
    assert "card ending: 0251" in _token(events)
    assert _result(events)["payload"] == {"executed": False, "cancelled": True}
    assert bank.freezes == []


# --- OTP verify errors --------------------------------------------------------


def test_wrong_otp_reports_attempts_and_does_not_resend(client, bank):
    _start(client, bank)
    bank.verify_errors.append(
        AdapterValidationError("OTP_INCORRECT", "Invalid OTP. 2 attempt(s) remaining.", attempts_remaining=2)
    )
    events = _post(client, "submit", {"otp": "1111", "pin": "123456"})
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["verificationStatus"] == "OTP_INCORRECT"
    assert result["payload"]["attemptsRemaining"] == 2
    assert "attempts left: 2" in _token(events)
    assert "no new code is needed" in _token(events)
    assert len(bank.sends) == 1
    assert bank.freezes == []

    # Retry with the right code succeeds.
    events = _post(client, "submit", {"otp": "0000", "pin": "123456"})
    assert _result(events)["payload"]["executed"] is True


def test_expired_otp_auto_resends(client, bank):
    _start(client, bank)
    bank.verify_errors.append(AdapterValidationError("OTP_EXPIRED", "No OTP on record"))
    events = _post(client, "submit", {"otp": "0000", "pin": "123456"})
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["verificationStatus"] == "OTP_RESENT"
    assert _token(events).startswith("verify:")
    assert "the earlier code expired, so a new one was sent" in _token(events)
    assert bank.sends == [CUSTOMER_PHONE, CUSTOMER_PHONE]
    assert bank.freezes == []


def test_blocked_otp_tells_customer_to_wait_and_ends_flow(client, bank):
    _start(client, bank)
    bank.verify_errors.append(AdapterValidationError("OTP_BLOCKED", "blocked"))
    events = _post(client, "submit", {"otp": "1111", "pin": "123456"})
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE"
    assert result["payload"] == {"executed": False, "verificationStatus": "OTP_BLOCKED"}
    assert "wait about 5 minutes" in _token(events)
    assert _token(events).startswith("not_done:")
    assert "card status: not frozen" in _token(events)
    assert bank.freezes == []


def test_send_throttled_at_start_tells_customer_to_wait(client, bank):
    bank.send_errors.append(AdapterValidationError("SEND_THROTTLED", "slow down"))
    _ask_freeze(client, bank)
    events = _post(client, "Confirm", {"confirm": True})
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE"
    assert result["payload"] == {"executed": False, "verificationStatus": "SEND_THROTTLED"}
    assert "wait a few minutes" in _token(events)


def test_send_unavailable_is_service_unavailable(client, bank):
    bank.send_errors.append(AdapterUnavailableError("down"))
    _ask_freeze(client, bank)
    events = _post(client, "Confirm", {"confirm": True})
    assert _result(events)["type"] == "SERVICE_UNAVAILABLE"


# --- freeze errors ------------------------------------------------------------


def test_wrong_pin_keeps_token_and_retries_without_resend_or_reverify(client, bank):
    _start(client, bank)
    bank.freeze_errors.append(AdapterValidationError("INVALID_CREDENTIALS", "bad pin"))
    events = _post(client, "submit", {"otp": "0000", "pin": "999999"})
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["verificationStatus"] == "INVALID_CREDENTIALS"
    assert result["payload"]["otpRequired"] is False
    assert "verificationToken" not in result["payload"]
    assert "the code is still valid, so only the PIN or password needs re-entering" in _token(events)

    # Retry with only the PIN: no new OTP send, no new verify, same token reused.
    events = _post(client, "submit", {"pin": "123456"})
    assert _result(events)["payload"]["executed"] is True
    assert len(bank.sends) == 1
    assert len(bank.verifies) == 1
    assert [f["verificationToken"] for f in bank.freezes] == ["vtoken-1", "vtoken-1"]


def test_invalid_verification_token_auto_resends(client, bank):
    _start(client, bank)
    bank.freeze_errors.append(AdapterValidationError("INVALID_VERIFICATION_TOKEN", "expired"))
    events = _post(client, "submit", {"otp": "0000", "pin": "123456"})
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["verificationStatus"] == "OTP_RESENT"
    assert result["payload"]["otpRequired"] is True
    assert _token(events).startswith("verify:")
    assert "the verification expired, so a new code was sent" in _token(events)
    assert len(bank.sends) == 2


def test_freeze_unavailable_never_claims_success(client, bank):
    _start(client, bank)
    bank.freeze_errors.append(AdapterUnavailableError("down"))
    events = _post(client, "submit", {"otp": "0000", "pin": "123456"})
    assert _result(events)["type"] == "SERVICE_UNAVAILABLE"
    assert "frozen" not in _token(events).lower()


# --- secrets never logged or persisted ---------------------------------------


def test_otp_pin_password_never_appear_in_logs_or_session_state(client, bank, caplog):
    """Runs the whole flow -- wrong PIN, password retry, plus a code typed straight
    into the chat box -- with distinctive secret values, then asserts none of them
    appear in ANY captured log record (request-entry logger, per-turn logger, audit
    logger) or in the stored session turns, while the real freeze call did receive
    them (the real payload is never mutated by redaction)."""
    secret_otp = "731942"
    secret_pin = "864209"
    secret_wrong_pin = "550173"
    secret_password = "Zq7!HorseBattery"
    typed_otp = "482916"
    secrets = [secret_otp, secret_pin, secret_wrong_pin, secret_password, typed_otp]

    caplog.set_level(logging.DEBUG)

    # Initial request already (wrongly) carries secrets -- they must not be stored.
    first = _post(client, "please freeze my card", {**CARD_PAYLOAD, "pin": secret_pin, "otp": secret_otp})
    assert _result(first)["type"] == "CONFIRMATION_REQUIRED"
    assert "pin" not in _result(first)["payload"] and "otp" not in _result(first)["payload"]
    confirm_events = _post(client, "Confirm", {"confirm": True})
    assert _result(confirm_events)["type"] == "OTP_REQUIRED"
    # Customer types a code into the chat box instead of the form.
    _post(client, f"the code is {typed_otp}")
    bank.freeze_errors.append(AdapterValidationError("INVALID_CREDENTIALS", "bad pin"))
    wrong_events = _post(client, "submit", {"otp": secret_otp, "pin": secret_wrong_pin})
    ok_events = _post(client, "submit", {"password": secret_password})

    assert _result(wrong_events)["payload"]["verificationStatus"] == "INVALID_CREDENTIALS"
    assert _result(ok_events)["payload"]["executed"] is True
    # The real calls got the real values (redaction never mutated them).
    assert bank.verifies == [(CUSTOMER_PHONE, secret_otp)]
    assert bank.freezes[0]["pin"] == secret_wrong_pin
    assert bank.freezes[1]["password"] == secret_password

    log_text = "\n".join(
        f"{record.name} {record.getMessage()}" for record in caplog.records
    )
    assert "chat.requests" in log_text and "banking.audit" in log_text
    stored_turns = session_module.get_session(CUSTOMER_PHONE)
    assert len(stored_turns) == 5
    session_text = repr(stored_turns)
    sse_text = json.dumps(first) + json.dumps(confirm_events) + json.dumps(wrong_events) + json.dumps(ok_events)

    for secret in secrets:
        assert secret not in log_text, f"secret leaked into logs: {secret}"
        assert secret not in session_text, f"secret leaked into session state: {secret}"
        assert secret not in sse_text, f"secret leaked into SSE output: {secret}"
    for turn in stored_turns:
        payload = (turn.classification or {}).get("payload") or {}
        assert not {"pin", "password", "otp"} & set(payload)


def test_redact_secrets_never_mutates_original():
    original = {"otp": "1", "pin": "2", "nested": {"password": "3"}, "cardId": "41"}
    redacted = chat_module._redact_secrets(original)
    assert redacted == {
        "otp": "[redacted]", "pin": "[redacted]", "nested": {"password": "[redacted]"}, "cardId": "41",
    }
    assert original == {"otp": "1", "pin": "2", "nested": {"password": "3"}, "cardId": "41"}
    assert chat_module._strip_secrets(original) == {"nested": {}, "cardId": "41"}
