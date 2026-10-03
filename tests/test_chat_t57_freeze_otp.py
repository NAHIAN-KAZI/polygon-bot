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


def _start(client, bank):
    events = _post(client, "please freeze my card")
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

    assert _token(events) == "Done — your card ending 0251 has been frozen."
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
    assert "just one" in _token(events)
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


def test_cancel_while_pending_stops_without_freezing(client, bank):
    _start(client, bank)
    events = _post(client, "cancel")
    assert _token(events) == "Okay, I won't freeze your card."
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
    assert "2 attempts left" in _token(events)
    assert "no new code" in _token(events)
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
    assert _token(events).startswith("That code has expired, so I've sent you a new one.")
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
    assert "has not been frozen" in _token(events)
    assert bank.freezes == []


def test_send_throttled_at_start_tells_customer_to_wait(client, bank):
    bank.send_errors.append(AdapterValidationError("SEND_THROTTLED", "slow down"))
    events = _post(client, "please freeze my card")
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE"
    assert result["payload"] == {"executed": False, "verificationStatus": "SEND_THROTTLED"}
    assert "wait a few minutes" in _token(events)


def test_send_unavailable_is_service_unavailable(client, bank):
    bank.send_errors.append(AdapterUnavailableError("down"))
    events = _post(client, "please freeze my card")
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
    assert "no new code" in _token(events)

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
    assert _token(events).startswith("Your verification has expired, so I've sent you a new code.")
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
    assert _result(first)["type"] == "OTP_REQUIRED"
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
    assert len(stored_turns) == 4
    session_text = repr(stored_turns)
    sse_text = json.dumps(first) + json.dumps(wrong_events) + json.dumps(ok_events)

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
