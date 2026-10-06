"""Tests for TASKS.md T-57 (card freeze) and T-60 (beneficiary add) -- this
chatbot's first-ever mutating platform calls, gated behind a deterministic
(never LLM) gather -> confirm -> execute flow in app/routes/chat.py.

Follows tests/test_chat_t58_new_services.py's conventions: classify/
verify_jwt/fulfill_banking_service/get_classification_context/get_session/
record_turn are monkeypatched at their app.routes.chat import sites, so
nothing here touches a live Ollama, the taxonomy cache, the real in-memory
session store, or (most importantly for this file) the real banking
platform -- no test here ever lets a freeze/beneficiary-add call reach a
real adapter with a verified "yes".
"""
import asyncio
import json

import httpx
import pytest

import app.routes.chat as chat_module
from app.banking.adapters.base import AdapterAuthError, AdapterResult, AdapterUnavailableError
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService
from app.banking.session import ChatTurn

from tests.conftest import AUTH_HEADERS

# Captured at import, before conftest's autouse fixture swaps in a stand-in.
_real_read_pending_reply = chat_module._read_pending_reply

CUSTOMER_ID = "cust-123"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}


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


def _install_identity_fakes(monkeypatch):
    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)


def _install_no_pending_session(monkeypatch):
    """No pending confirmation/clarification -- a fresh request."""
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [])
    monkeypatch.setattr(chat_module, "get_session", lambda customer_id: [])
    monkeypatch.setattr(chat_module, "record_turn", lambda *a, **k: None)


def _install_pending_confirmation_session(monkeypatch, classification: dict):
    turn = ChatTurn(timestamp=None, message="prior message", classification=classification)
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [])
    monkeypatch.setattr(chat_module, "get_session", lambda customer_id: [turn])
    monkeypatch.setattr(chat_module, "record_turn", lambda *a, **k: None)


def _fail_classify(monkeypatch):
    """Any test exercising the pending-confirmation branch must never reach
    classify() -- wire it to blow up loudly if it ever is."""
    async def fake_classify(message, recent_turns=None):
        raise AssertionError("classify() must not be called while a confirmation is pending")

    monkeypatch.setattr(chat_module, "classify", fake_classify)


# --- _read_pending_reply: the model reads a typed reply; a confirm counts -----
# --- only when grounded in the customer's own words (T-77) -------------------


class _ModelReply:
    def __init__(self, obj):
        self._obj = obj

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": json.dumps(self._obj)}


def _model_says(monkeypatch, obj):
    async def fake_post(self, url, *args, **kwargs):
        return _ModelReply(obj)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def _read(message):
    return asyncio.run(_real_read_pending_reply("Shall I add Rahim?", message, None))


@pytest.mark.parametrize(
    "message",
    ["yes", "Yes", "YES!", "confirm", "Confirmed.", "do it", "Do it!", "go ahead", "yes please"],
)
def test_classify_confirmation_reply_affirmative(monkeypatch, message):
    _model_says(monkeypatch, {"answer": "confirm", "quote": message})
    assert _read(message) == "confirm"


@pytest.mark.parametrize(
    "message", ["no", "No.", "cancel", "Cancel!", "nevermind", "never mind", "stop", "Stop."]
)
def test_classify_confirmation_reply_negative(monkeypatch, message):
    _model_says(monkeypatch, {"answer": "decline", "quote": message})
    assert _read(message) == "decline"


@pytest.mark.parametrize(
    "message", ["maybe", "I'm not sure", "yes but wait", "freeze it", "yesss"]
)
def test_classify_confirmation_reply_unclear(monkeypatch, message):
    _model_says(monkeypatch, {"answer": "unsure", "quote": message})
    assert _read(message) == "unsure"


@pytest.mark.parametrize("message", ["maybe", "hmm", "what does that mean"])
def test_confirm_without_the_customers_own_words_is_unsure(monkeypatch, message):
    # The model claims a "yes" the customer never wrote: nothing runs on it.
    _model_says(monkeypatch, {"answer": "confirm", "quote": "yes go ahead"})
    assert _read(message) == "unsure"


# --- T-57: card freeze gather step ------------------------------------------


def test_freeze_card_zero_cards_is_clean_no_error(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="card_services", service="frezz_unfrezz", subservice=None, payload={})

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        assert (category, service) == ("account_info", "cards")
        return AdapterResult(data={"cards": []})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_identity_fakes(monkeypatch)
    _install_no_pending_session(monkeypatch)

    resp = client.post("/chat", json={"message": "freeze my card"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("answer:")
    assert "cards on file: none" in token_event["token"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"] == {"cards": []}


def test_freeze_card_one_card_auto_selects_then_asks_reason(client, monkeypatch):
    card = {"id": "41", "cardType": "DEBIT", "cardNumber": "4001****0251", "status": "ACTIVE"}

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="card_services", service="frezz_unfrezz", subservice=None, payload={})

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"cards": [card]})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_identity_fakes(monkeypatch)
    _install_no_pending_session(monkeypatch)

    resp = client.post("/chat", json={"message": "freeze my card"}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert "reason" in token_event["token"].lower()
    assert "0251" in token_event["token"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"


def test_freeze_card_two_cards_asks_which_one(client, monkeypatch):
    cards = [
        {"id": "41", "cardType": "DEBIT", "cardNumber": "4001****0251", "status": "ACTIVE"},
        {"id": "42", "cardType": "CREDIT", "cardNumber": "5300****9988", "status": "ACTIVE"},
    ]

    async def fake_classify(message, recent_turns=None):
        return BankingService(category="card_services", service="frezz_unfrezz", subservice=None, payload={})

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"cards": cards})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_identity_fakes(monkeypatch)
    _install_no_pending_session(monkeypatch)

    resp = client.post("/chat", json={"message": "freeze my card"}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "ACCOUNT_SELECTION_REQUIRED"
    assert result_event["payload"] == {"accounts": cards}

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("choose:")
    assert "Debit card ending 0251" in token_event["token"] and "Credit card ending 9988" in token_event["token"]


def test_freeze_card_id_and_reason_known_sends_otp_and_asks_for_otp_and_pin(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="card_services",
            service="frezz_unfrezz",
            subservice=None,
            payload={"cardId": "41", "cardLast4": "0251", "reason": "lost"},
        )

    fulfill_calls = []

    async def fake_fulfill(*a, **k):
        fulfill_calls.append((a, k))
        raise AssertionError("the real adapter must never be called before OTP + PIN/password")

    otp_sends = []

    async def fake_send_otp(phone):
        otp_sends.append(phone)

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "send_otp", fake_send_otp)
    _install_identity_fakes(monkeypatch)
    _install_no_pending_session(monkeypatch)

    # Step 1: the request ends in a yes/no; no verification code is sent yet.
    resp = client.post("/chat", json={"message": "freeze my card"}, headers=JWT_HEADERS)
    asked = _parse_sse(resp.text)
    assert next(data for name, data in asked if name == "result")["type"] == "CONFIRMATION_REQUIRED"
    assert next(data for name, data in asked if name == "token")["token"].startswith("confirm:")
    assert otp_sends == [] and fulfill_calls == []

    # Step 2: the customer confirms (the app's button) -> the code goes to their own phone.
    pending = {"type": "CONFIRMATION_REQUIRED", "category": "card_services", "service": "frezz_unfrezz",
               "subservice": None, "payload": {"cardId": "41", "cardLast4": "0251", "reason": "lost"},
               "question": "confirm: ..."}
    _install_pending_confirmation_session(monkeypatch, pending)
    resp = client.post("/chat", json={"message": "Confirm", "payload": {"confirm": True}}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]
    assert fulfill_calls == []
    assert otp_sends == [CUSTOMER_ID]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("verify:")
    assert "one-time code" in token_event["token"]
    assert "card ending: 0251" in token_event["token"]
    assert "PIN" in token_event["token"] and "password" in token_event["token"]
    assert "secure form" in token_event["token"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "OTP_REQUIRED"
    assert result_event["category"] == "card_services"
    assert result_event["service"] == "frezz_unfrezz"
    assert result_event["payload"] == {
        "cardId": "41",
        "cardLast4": "0251",
        "reason": "lost",
        "otpRequired": True,
        "credentialOptions": ["pin", "password"],
        "verificationStatus": "OTP_SENT",
    }


# Note: this test drives the explicit category+service request path, which
# normally validates against is_valid_path (always False in this test
# environment per test_chat_contract_extension.py's own note, since the
# taxonomy cache is never populated outside the app's real startup
# lifespan). We route via a mocked classify() instead in the other tests;
# this one needs the explicit path specifically (to prove fulfill_banking_service
# is never called pre-confirmation even on a direct resubmit), so it patches
# is_valid_path too.
def test_freeze_card_explicit_resubmit_uses_is_valid_path(client, monkeypatch):
    monkeypatch.setattr(chat_module, "is_valid_path", lambda *a, **k: True)
    _install_identity_fakes(monkeypatch)
    _install_no_pending_session(monkeypatch)

    async def fake_fulfill(*a, **k):
        raise AssertionError("must not be called before OTP + PIN/password")

    otp_sends = []

    async def fake_send_otp(phone):
        otp_sends.append(phone)

    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "send_otp", fake_send_otp)

    resp = client.post(
        "/chat",
        json={
            "category": "card_services",
            "service": "frezz_unfrezz",
            "message": "freeze it",
            # A phone in the payload must never be used -- the OTP always goes to
            # the phone from the customer's own verified JWT identity.
            "payload": {"cardId": "41", "reason": "stolen", "phone": "01700000000"},
        },
        headers=JWT_HEADERS,
    )
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    # Even a direct resubmit from the app ends in a yes/no first: no code yet.
    assert result_event["type"] == "CONFIRMATION_REQUIRED"
    assert result_event["payload"] == {"cardId": "41", "reason": "stolen", "phone": "01700000000"}
    assert otp_sends == []

    # Confirming sends the code to the JWT customer, never the payload's phone.
    pending = {"type": "CONFIRMATION_REQUIRED", "category": "card_services", "service": "frezz_unfrezz",
               "subservice": None, "payload": {"cardId": "41", "reason": "stolen", "phone": "01700000000"},
               "question": "confirm: ..."}
    _install_pending_confirmation_session(monkeypatch, pending)
    resp = client.post("/chat", json={"message": "Confirm", "payload": {"confirm": True}}, headers=JWT_HEADERS)
    result_event = next(data for name, data in _parse_sse(resp.text) if name == "result")
    assert result_event["type"] == "OTP_REQUIRED"
    assert otp_sends == [CUSTOMER_ID]


# --- T-60: beneficiary add gather step --------------------------------------


def test_beneficiary_add_missing_both_fields_asks_for_both(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="beneficiary_management", service="beneficiary_add", subservice=None, payload={})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    _install_identity_fakes(monkeypatch)
    _install_no_pending_session(monkeypatch)

    resp = client.post("/chat", json={"message": "add a beneficiary"}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"

    token_event = next(data for name, data in events if name == "token")
    assert "name" in token_event["token"].lower()
    assert "account number" in token_event["token"].lower()


def test_beneficiary_add_complete_payload_asks_for_confirmation(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="beneficiary_management",
            service="beneficiary_add",
            subservice=None,
            payload={"nickname": "Rahim", "accountNumber": "1234567890"},
        )

    async def fake_fulfill(*a, **k):
        raise AssertionError("must not call the real adapter before confirmation")

    async def fake_lookup(jwt, identifier):
        assert identifier == "1234567890"
        return {"accountNumber": "1234567890", "accountName": "Rahim Uddin"}

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "lookup_recipient", fake_lookup)
    _install_identity_fakes(monkeypatch)
    _install_no_pending_session(monkeypatch)

    resp = client.post("/chat", json={"message": "add Rahim, account 1234567890"}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("confirm:")
    assert "nickname: Rahim" in token_event["token"]
    assert "account holder: Rahim Uddin" in token_event["token"]
    assert "account ending: 7890" in token_event["token"]
    assert "1234567890" not in token_event["token"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CONFIRMATION_REQUIRED"
    assert result_event["category"] == "beneficiary_management"
    assert result_event["service"] == "beneficiary_add"
    # The bank's recipient lookup found a Polygon Bank account: OWN_BANK, with the
    # bank's own identifierType value ("ACCOUNT" -- "ACCOUNT_NUMBER" is a 500).
    assert result_event["payload"] == {
        "nickname": "Rahim",
        "accountNumber": "1234567890",
        "serviceType": "OWN_BANK",
        "identifierType": "ACCOUNT",
        "accountHolderName": "Rahim Uddin",
    }


# --- pending confirmation: affirmative / negative / unclear -----------------


def test_pending_freeze_confirmation_yes_only_sends_the_code_never_freezes(client, monkeypatch):
    """The freeze yes/no comes BEFORE the verification code: a yes sends the code to
    the customer's own phone and moves to the OTP step; the real freeze adapter is
    only ever reached after the OTP step."""
    pending = {
        "type": "CONFIRMATION_REQUIRED",
        "category": "card_services",
        "service": "frezz_unfrezz",
        "subservice": None,
        "payload": {"cardId": "41", "cardLast4": "0251", "reason": "lost"},
        "question": "Shall I proceed? (yes/no)",
    }

    async def fake_fulfill(*a, **k):
        raise AssertionError("a bare yes must never freeze a card")

    sends = []

    async def fake_send_otp(phone):
        sends.append(phone)

    async def fake_classify(message, recent_turns=None):
        raise AssertionError("a reply to the pending yes/no is never re-classified")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module, "send_otp", fake_send_otp)
    _install_identity_fakes(monkeypatch)
    _install_pending_confirmation_session(monkeypatch, pending)

    resp = client.post("/chat", json={"message": "yes"}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "OTP_REQUIRED"
    assert sends == [CUSTOMER_ID]


def test_pending_beneficiary_confirmation_affirmative_calls_adapter(client, monkeypatch):
    pending = {
        "type": "CONFIRMATION_REQUIRED",
        "category": "beneficiary_management",
        "service": "beneficiary_add",
        "subservice": None,
        "payload": {
            "nickname": "Rahim",
            "accountNumber": "1234567890",
            "serviceType": "OTHER_BANK",
            "identifierType": "ACCOUNT_NUMBER",
        },
        "question": "Shall I proceed? (yes/no)",
    }
    fulfill_calls = []

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        fulfill_calls.append((category, service, subservice, payload))
        return AdapterResult(data={"id": 99, "nickname": "Rahim"})

    _fail_classify(monkeypatch)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_identity_fakes(monkeypatch)
    _install_pending_confirmation_session(monkeypatch, pending)

    resp = client.post("/chat", json={"message": "confirm"}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    assert len(fulfill_calls) == 1
    category, service, subservice, payload = fulfill_calls[0]
    assert (category, service, subservice) == ("beneficiary_management", "beneficiary_add", None)
    assert payload["serviceType"] == "OTHER_BANK"

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("done:")
    assert "nickname: Rahim" in token_event["token"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"]["executed"] is True


def test_pending_confirmation_negative_never_calls_adapter(client, monkeypatch):
    pending = {
        "type": "CONFIRMATION_REQUIRED",
        "category": "beneficiary_management",
        "service": "beneficiary_add",
        "subservice": None,
        "payload": {"nickname": "Rahim", "accountNumber": "1234567890"},
        "question": "Shall I proceed? (yes/no)",
    }
    fulfill_calls = []

    async def fake_fulfill(*a, **k):
        fulfill_calls.append((a, k))
        return AdapterResult(data={})

    _fail_classify(monkeypatch)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_identity_fakes(monkeypatch)
    _install_pending_confirmation_session(monkeypatch, pending)

    resp = client.post("/chat", json={"message": "no"}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    assert fulfill_calls == []

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("declined:")

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"] == {"executed": False, "cancelled": True}


def test_pending_confirmation_unclear_reasks_and_never_calls_adapter(client, monkeypatch):
    pending = {
        "type": "CONFIRMATION_REQUIRED",
        "category": "beneficiary_management",
        "service": "beneficiary_add",
        "subservice": None,
        "payload": {"nickname": "Rahim", "accountNumber": "1234567890"},
        "question": "You're about to add Rahim as a beneficiary. Shall I proceed? (yes/no)",
    }
    fulfill_calls = []

    async def fake_fulfill(*a, **k):
        fulfill_calls.append((a, k))
        return AdapterResult(data={})

    _fail_classify(monkeypatch)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_identity_fakes(monkeypatch)
    _install_pending_confirmation_session(monkeypatch, pending)

    resp = client.post("/chat", json={"message": "maybe later"}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    assert fulfill_calls == []

    token_event = next(data for name, data in events if name == "token")
    # re-asks the same yes/no with the same exact values
    assert token_event["token"].startswith("confirm:")
    assert "nickname: Rahim" in token_event["token"]
    assert "account ending: 7890" in token_event["token"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CONFIRMATION_REQUIRED"
    assert result_event["payload"] == {"nickname": "Rahim", "accountNumber": "1234567890"}


def test_pending_confirmation_affirmative_adapter_unavailable_never_claims_success(client, monkeypatch):
    pending = {
        "type": "CONFIRMATION_REQUIRED",
        "category": "beneficiary_management",
        "service": "beneficiary_add",
        "subservice": None,
        "payload": {"nickname": "Rahim", "accountNumber": "1234567890"},
        "question": "Shall I proceed? (yes/no)",
    }

    async def fake_fulfill(*a, **k):
        raise AdapterUnavailableError("beneficiary service down")

    _fail_classify(monkeypatch)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_identity_fakes(monkeypatch)
    _install_pending_confirmation_session(monkeypatch, pending)

    resp = client.post("/chat", json={"message": "yes"}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("unavailable:")
    assert not token_event["token"].startswith("done:")
    assert "added" not in token_event["token"].lower()

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "SERVICE_UNAVAILABLE"


def test_pending_confirmation_affirmative_adapter_auth_error(client, monkeypatch):
    pending = {
        "type": "CONFIRMATION_REQUIRED",
        "category": "beneficiary_management",
        "service": "beneficiary_add",
        "subservice": None,
        "payload": {"nickname": "Rahim", "accountNumber": "123"},
        "question": "Shall I proceed? (yes/no)",
    }

    async def fake_fulfill(*a, **k):
        raise AdapterAuthError

    _fail_classify(monkeypatch)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_identity_fakes(monkeypatch)
    _install_pending_confirmation_session(monkeypatch, pending)

    resp = client.post("/chat", json={"message": "go ahead"}, headers=JWT_HEADERS)

    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "AUTH_REQUIRED"


def test_pending_confirmation_only_applies_to_free_text_not_explicit_requests(client, monkeypatch):
    """An explicit category+service resubmit is always a fresh request, never
    treated as answering a pending confirmation -- even if one happens to be
    pending in the session (e.g. the customer navigated away and used a
    different in-app flow)."""
    pending = {
        "type": "CONFIRMATION_REQUIRED",
        "category": "card_services",
        "service": "frezz_unfrezz",
        "subservice": None,
        "payload": {"cardId": "41", "reason": "lost"},
        "question": "Shall I proceed? (yes/no)",
    }
    monkeypatch.setattr(chat_module, "is_valid_path", lambda *a, **k: False)
    _install_identity_fakes(monkeypatch)
    _install_pending_confirmation_session(monkeypatch, pending)

    async def fake_fulfill(*a, **k):
        raise AssertionError("must not be called")

    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)

    resp = client.post(
        "/chat",
        json={"message": "something else", "category": "billing", "service": "payments"},
        headers=JWT_HEADERS,
    )
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "UNKNOWN_SERVICE"
