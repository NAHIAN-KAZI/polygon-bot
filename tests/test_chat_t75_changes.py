"""T-75: customer-requested changes -- complaint, nickname, address (explicit yes),
email / mobile (verified OTP), report lost card and profile photo (redirect only,
never a bank call from chat).

Nothing here reaches the network: adapter tests replace app.banking.adapters.real._call,
and chat tests replace send_otp / verify_otp / fulfill_banking_service / classify /
verify_jwt at their app.routes.chat import sites. Multi-turn flows use the REAL
in-memory session store (reset per test) so pending CONFIRMATION_REQUIRED /
OTP_REQUIRED state carries across turns exactly as in production.
"""
import asyncio
import json

import pytest

import app.banking.adapters.real as real_module
import app.banking.session as session_module
import app.banking.taxonomy as taxonomy_module
import app.routes.chat as chat_module
from app.banking.adapter_map import get_adapter_name
from app.banking.adapters.base import (
    AdapterResult,
    AdapterUnavailableError,
    AdapterValidationError,
)
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, Clarification

from tests.conftest import AUTH_HEADERS

CUSTOMER_PHONE = "01712345678"
NEW_PHONE = "01898765432"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}


# --- SSE helpers --------------------------------------------------------------


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


def _post(client, message, payload=None, **extra):
    body = {"message": message, **extra}
    if payload is not None:
        body["payload"] = payload
    resp = client.post("/chat", json=body, headers=JWT_HEADERS)
    assert resp.status_code == 200
    return _parse_sse(resp.text)


# --- adapters: request path / body (mocked _call) -----------------------------


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    async def fake_call(method, path, jwt, *, params=None, json=None):
        recorded.append({"method": method, "path": path, "jwt": jwt, "params": params, "json": json})
        return {"success": True}

    monkeypatch.setattr(real_module, "_call", fake_call)
    return recorded


def _fulfill(adapter_id, payload):
    adapter = real_module.REAL_ADAPTERS[f"real:{adapter_id}"]
    return asyncio.run(adapter.fulfill(CustomerIdentity(customer_id=CUSTOMER_PHONE), "jwt-x", None, payload))


def test_new_adapters_are_registered_and_mapped():
    for adapter_id in ("submit_complaint", "update_nickname", "update_address", "update_email", "update_mobile"):
        assert f"real:{adapter_id}" in real_module.REAL_ADAPTERS
    assert get_adapter_name("support", "submit_complaint") == "real:submit_complaint"
    assert get_adapter_name("profile_update", "update_nickname") == "real:update_nickname"
    assert get_adapter_name("profile_update", "update_address") == "real:update_address"
    assert get_adapter_name("profile_update", "update_email") == "real:update_email"
    assert get_adapter_name("profile_update", "update_mobile") == "real:update_mobile"
    # Redirect-only services never get a real adapter.
    assert get_adapter_name("card_requests", "report_lost_card") == "mock"
    assert get_adapter_name("profile_update", "update_profile_image") == "mock"


def test_complaint_adapter_posts_category_and_description(calls):
    result = _fulfill("submit_complaint", {"category": "CARD", "description": "ATM ate my card"})
    assert calls == [{
        "method": "POST", "path": "/support/v1/complaints", "jwt": "jwt-x", "params": None,
        "json": {"category": "CARD", "description": "ATM ate my card"},
    }]
    assert isinstance(result, AdapterResult)


def test_complaint_adapter_unknown_category_becomes_other_and_truncates(calls):
    _fulfill("submit_complaint", {"category": "WEIRD", "description": "x" * 2500})
    body = calls[0]["json"]
    assert body["category"] == "OTHER"
    assert len(body["description"]) == 2000


def test_complaint_adapter_missing_description_never_calls_bank(calls):
    with pytest.raises(AdapterUnavailableError):
        _fulfill("submit_complaint", {"category": "CARD"})
    assert calls == []


def test_nickname_adapter_patches_nickname_with_capital_n(calls):
    _fulfill("update_nickname", {"nickName": "  Rafi  "})
    assert calls[0]["method"] == "PATCH"
    assert calls[0]["path"] == "/auth/v1/user/profile/nickname"
    assert calls[0]["json"] == {"nickName": "Rafi"}


def test_nickname_adapter_missing_value_never_calls_bank(calls):
    with pytest.raises(AdapterUnavailableError):
        _fulfill("update_nickname", {})
    assert calls == []


def test_address_adapter_sends_only_present_address_fields(calls):
    _fulfill("update_address", {
        "presentAddress": " House 1, Road 2, Dhaka ", "district": "", "division": None, "foo": "bar",
    })
    assert calls[0]["method"] == "PATCH"
    assert calls[0]["path"] == "/customer/v1/me/demographic"
    assert calls[0]["json"] == {"presentAddress": "House 1, Road 2, Dhaka"}


def test_address_adapter_all_fields(calls):
    payload = {"presentAddress": "A", "permanentAddress": "B", "district": "Dhaka", "division": "Dhaka"}
    _fulfill("update_address", payload)
    assert calls[0]["json"] == payload
    assert set(real_module.ADDRESS_FIELDS) == set(payload)


def test_address_adapter_no_field_never_calls_bank(calls):
    with pytest.raises(AdapterUnavailableError):
        _fulfill("update_address", {"foo": "bar"})
    assert calls == []


def test_email_adapter_posts_new_email_and_token(calls):
    _fulfill("update_email", {"newEmail": "a@b.com", "verificationToken": "vt", "junk": 1})
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/auth/v1/auth/email/update"
    assert calls[0]["json"] == {"newEmail": "a@b.com", "verificationToken": "vt"}


def test_email_adapter_without_token_never_calls_bank(calls):
    with pytest.raises(AdapterUnavailableError):
        _fulfill("update_email", {"newEmail": "a@b.com"})
    assert calls == []


def test_mobile_adapter_posts_new_phone_and_token(calls):
    _fulfill("update_mobile", {"newPhone": NEW_PHONE, "verificationToken": "vt"})
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/auth/v1/auth/mobile/update"
    assert calls[0]["json"] == {"newPhone": NEW_PHONE, "verificationToken": "vt"}


def test_mobile_adapter_without_token_never_calls_bank(calls):
    with pytest.raises(AdapterUnavailableError):
        _fulfill("update_mobile", {"newPhone": NEW_PHONE})
    assert calls == []


def test_complaint_categories_constant():
    assert real_module.COMPLAINT_CATEGORIES == (
        "ACCOUNT", "CARD", "TRANSACTION", "LOAN_DEPOSIT", "MOBILE_APP_TECHNICAL", "SERVICE_QUALITY", "OTHER",
    )


# --- taxonomy -------------------------------------------------------------------


def test_synthetic_categories_are_valid_paths(monkeypatch):
    async def no_platform():
        return []

    monkeypatch.setattr(taxonomy_module, "_fetch_merged_categories", no_platform)
    _, index = asyncio.run(taxonomy_module._fetch_and_build())
    monkeypatch.setattr(taxonomy_module, "_index", index)
    for category, service in [
        ("card_requests", "report_lost_card"),
        ("support", "submit_complaint"),
        ("profile_update", "update_nickname"),
        ("profile_update", "update_address"),
        ("profile_update", "update_email"),
        ("profile_update", "update_mobile"),
        ("profile_update", "update_profile_image"),
    ]:
        assert taxonomy_module.is_valid_path(category, service), (category, service)


# --- _normalize_change_request --------------------------------------------------


def _norm(category, service, payload):
    return chat_module._normalize_change_request(BankingService(category, service, None, payload))


@pytest.mark.parametrize("given,expected", [
    ("card", "CARD"), ("  service_quality ", "SERVICE_QUALITY"), ("nonsense", "OTHER"), (None, "OTHER"),
])
def test_normalize_complaint_category(given, expected):
    result = _norm("support", "submit_complaint", {"category": given, "description": " slow app "})
    assert result.payload == {"category": expected, "description": "slow app"}


def test_normalize_complaint_description_truncated():
    result = _norm("support", "submit_complaint", {"description": "y" * 3000})
    assert len(result.payload["description"]) == 2000


def test_normalize_complaint_missing_description_is_not_invented():
    result = _norm("support", "submit_complaint", {})
    assert result.payload == {"category": "OTHER"}
    assert chat_module._missing_payload_fields("support", "submit_complaint", result.payload) == ["description"]


@pytest.mark.parametrize("given,expected", [
    ("Rafi", "Rafi"), ('  "Rafi"  ', "Rafi"), ("x" * 50, "x" * 50), ("x" * 51, None), ("   ", None), (None, None),
])
def test_normalize_nickname(given, expected):
    result = _norm("profile_update", "update_nickname", {"nickName": given})
    assert (result.payload or {}).get("nickName") == expected


@pytest.mark.parametrize("given,expected", [
    ("New@Example.COM ", "new@example.com"), ("not-an-email", None), ("a@b", None), ("a b@c.com", None),
])
def test_normalize_email(given, expected):
    result = _norm("profile_update", "update_email", {"newEmail": given})
    assert (result.payload or {}).get("newEmail") == expected


@pytest.mark.parametrize("given,expected", [
    ("01898765432", "01898765432"),
    ("+8801898765432", "01898765432"),
    ("8801898765432", "01898765432"),
    ("018-9876-5432", "01898765432"),
    ("01298765432", None),   # operator digit must be 3-9
    ("0189876543", None),    # too short
    ("018987654321", None),  # too long
    ("hello", None),
])
def test_normalize_mobile(given, expected):
    result = _norm("profile_update", "update_mobile", {"newPhone": given})
    assert (result.payload or {}).get("newPhone") == expected


@pytest.mark.parametrize("given,expected", [
    ("stolen", "STOLEN"), ("LOST", "LOST"), ("damaged", "DAMAGED"), ("broken", None),
])
def test_normalize_report_lost_reason_code(given, expected):
    result = _norm("card_requests", "report_lost_card", {"reasonCode": given, "cardId": "41"})
    assert result.payload.get("reasonCode") == expected
    assert result.payload["cardId"] == "41"


def test_normalize_invalid_value_dropped_so_it_is_asked_again():
    result = _norm("profile_update", "update_email", {"newEmail": "nope"})
    assert result.payload is None
    assert chat_module._missing_payload_fields("profile_update", "update_email", result.payload) == ["newEmail"]


def test_normalize_leaves_other_services_and_non_banking_untouched():
    original = BankingService("account_info", "balance", None, {"x": "y"})
    assert chat_module._normalize_change_request(original) is original
    clar = Clarification(question="?")
    assert chat_module._normalize_change_request(clar) is clar


# --- _missing_payload_fields: address needs at least one field -------------------


@pytest.mark.parametrize("payload,expected", [
    (None, ["newAddress"]),
    ({}, ["newAddress"]),
    ({"presentAddress": ""}, ["newAddress"]),
    ({"foo": "bar"}, ["newAddress"]),
    ({"presentAddress": "Dhaka"}, []),
    ({"permanentAddress": "Sylhet"}, []),
    ({"district": "Dhaka"}, []),
    ({"division": "Khulna"}, []),
])
def test_address_missing_field_rule(payload, expected):
    assert chat_module._missing_payload_fields("profile_update", "update_address", payload) == expected


# --- chat flow fixture ------------------------------------------------------------


class FakeBank:
    def __init__(self):
        self.sends: list[str] = []
        self.verifies: list[tuple[str, str]] = []
        self.fulfills: list[tuple[str, str, dict | None]] = []
        self.send_errors: list[Exception] = []
        self.verify_errors: list[Exception] = []
        self.cards: list[dict] = [{"id": "41", "cardNumber": "4001230000000251", "status": "ACTIVE"}]
        self.routes: dict[str, object] = {}
        self.classify_calls: list[str] = []

    async def send_otp(self, phone):
        self.sends.append(phone)
        if self.send_errors:
            raise self.send_errors.pop(0)

    async def verify_otp(self, phone, otp):
        self.verifies.append((phone, otp))
        if self.verify_errors:
            raise self.verify_errors.pop(0)
        return "vtoken-1"

    async def fulfill(self, customer_identity, jwt, category, service, subservice, payload):
        self.fulfills.append((category, service, dict(payload) if payload else payload))
        if (category, service) == ("account_info", "cards"):
            return AdapterResult(data={"cards": self.cards})
        return AdapterResult(data={"success": True})

    def mutating_calls(self):
        return [f for f in self.fulfills if (f[0], f[1]) != ("account_info", "cards")]

    async def classify(self, message, recent_turns=None):
        self.classify_calls.append(message)
        for needle, result in self.routes.items():
            if needle in message.lower():
                return result
        return Clarification(question="What would you like to do?")


@pytest.fixture
def bank(monkeypatch):
    monkeypatch.setattr(session_module, "_sessions", {})
    fake = FakeBank()

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_PHONE)

    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "classify", fake.classify)
    monkeypatch.setattr(chat_module, "send_otp", fake.send_otp)
    monkeypatch.setattr(chat_module, "verify_otp", fake.verify_otp)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake.fulfill)
    return fake


def _no_phrase(monkeypatch):
    """_phrase must never reword a confirmation question -- fail loudly if called on one."""
    async def guard(facts, customer_message):
        assert "(yes/no)" not in facts, f"confirmation question was sent through _phrase: {facts}"
        return facts

    monkeypatch.setattr(chat_module, "_phrase", guard)


# --- yes/no confirmations: complaint / nickname / address -------------------------

CONFIRM_CASES = [
    pytest.param(
        BankingService("support", "submit_complaint", None,
                       {"category": "service_quality", "description": "The branch staff were rude"}),
        ("support", "submit_complaint", {"category": "SERVICE_QUALITY", "description": "The branch staff were rude"}),
        ['"The branch staff were rude"', "service quality"],
        "Okay, I won't submit the complaint.",
        id="complaint",
    ),
    pytest.param(
        BankingService("profile_update", "update_nickname", None, {"nickName": "Rafi"}),
        ("profile_update", "update_nickname", {"nickName": "Rafi"}),
        ['"Rafi"'],
        "Okay, I won't change your nickname.",
        id="nickname",
    ),
    pytest.param(
        BankingService("profile_update", "update_address", None,
                       {"presentAddress": "House 5, Road 7, Dhanmondi", "district": "Dhaka"}),
        ("profile_update", "update_address", {"presentAddress": "House 5, Road 7, Dhanmondi", "district": "Dhaka"}),
        ["present address: House 5, Road 7, Dhanmondi", "district: Dhaka"],
        "Okay, I won't change your address.",
        id="address",
    ),
]


@pytest.mark.parametrize("route,expected_call,question_bits,decline", CONFIRM_CASES)
def test_confirmation_yes_executes_once_with_payload(client, bank, monkeypatch, route, expected_call, question_bits, decline):
    _no_phrase(monkeypatch)
    bank.routes["please change"] = route
    events = _post(client, "please change this")
    result = _result(events)
    assert result["type"] == "CONFIRMATION_REQUIRED"
    question = _token(events)
    assert question.endswith("(yes/no)")
    for bit in question_bits:
        assert bit in question
    assert bank.mutating_calls() == []

    events = _post(client, "yes")
    assert _result(events)["type"] == "BANKING_SERVICE"
    assert _token(events).startswith("Done")
    assert bank.mutating_calls() == [expected_call]
    assert bank.classify_calls == ["please change this"]


@pytest.mark.parametrize("route,expected_call,question_bits,decline", CONFIRM_CASES)
def test_confirmation_no_never_executes(client, bank, route, expected_call, question_bits, decline):
    bank.routes["please change"] = route
    _post(client, "please change this")
    events = _post(client, "no")
    assert _token(events) == decline
    assert _result(events)["payload"] == {"executed": False, "cancelled": True}
    assert bank.mutating_calls() == []
    # Flow is over: a later "yes" doesn't revive it.
    _post(client, "yes")
    assert bank.mutating_calls() == []


def test_address_without_any_field_asks_and_never_confirms(client, bank):
    bank.routes["address"] = BankingService("profile_update", "update_address", None, {})
    events = _post(client, "change my address")
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"
    assert bank.mutating_calls() == []


def test_invalid_nickname_is_asked_again_not_confirmed(client, bank):
    bank.routes["nickname"] = BankingService("profile_update", "update_nickname", None, {"nickName": "x" * 60})
    events = _post(client, "change my nickname")
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"
    assert bank.mutating_calls() == []


# --- confirmation escape: long unclear reply drops the pending change -------------


def test_long_unclear_reply_drops_pending_change_and_is_reclassified(client, bank):
    bank.routes["nickname"] = BankingService("profile_update", "update_nickname", None, {"nickName": "Rafi"})
    _post(client, "change my nickname")
    events = _post(client, "what is my balance")
    assert bank.classify_calls == ["change my nickname", "what is my balance"]
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"  # FakeBank's default classification
    assert bank.mutating_calls() == []
    # The dropped change stays dropped.
    _post(client, "yes")
    assert bank.mutating_calls() == []


def test_long_reply_starting_with_yes_is_not_treated_as_yes(client, bank):
    bank.routes["nickname"] = BankingService("profile_update", "update_nickname", None, {"nickName": "Rafi"})
    _post(client, "change my nickname")
    _post(client, "yes but wait a second")
    assert bank.mutating_calls() == []
    assert bank.classify_calls[-1] == "yes but wait a second"


@pytest.mark.parametrize("reply", ["maybe", "hmm okay"])
def test_short_unclear_reply_reasks_without_classifying(client, bank, reply):
    bank.routes["nickname"] = BankingService("profile_update", "update_nickname", None, {"nickName": "Rafi"})
    first = _post(client, "change my nickname")
    question = _token(first)
    events = _post(client, reply)
    assert _result(events)["type"] == "CONFIRMATION_REQUIRED"
    assert _token(events) == f"Sorry, I didn't quite catch that — {question}"
    assert bank.classify_calls == ["change my nickname"]
    assert bank.mutating_calls() == []
    # Still pending: a yes now executes.
    _post(client, "yes")
    assert bank.mutating_calls() == [("profile_update", "update_nickname", {"nickName": "Rafi"})]


# --- report lost card: redirect only, never a bank mutation ----------------------


def test_report_lost_card_with_card_known_never_calls_bank(client, bank):
    bank.routes["stolen"] = BankingService(
        "card_requests", "report_lost_card", None, {"cardId": "41", "cardLast4": "0251", "reasonCode": "stolen"},
    )
    events = _post(client, "my card was stolen")
    result = _result(events)
    assert bank.fulfills == []
    assert bank.sends == []
    assert result["type"] == "BANKING_SERVICE"
    assert result["routing"]["action"] == "report_lost_card"
    assert result["payload"] == {"cardId": "41", "cardLast4": "0251", "reasonCode": "STOLEN", "executed": False}
    assert "card ending 0251 is stolen" in _token(events)
    assert "can't be undone" in _token(events)


def test_report_lost_card_resolves_single_card_via_lookup_only(client, bank):
    bank.routes["lost"] = BankingService("card_requests", "report_lost_card", None, {"reasonCode": "LOST"})
    events = _post(client, "I lost my card")
    result = _result(events)
    # The only bank call is the read-only card lookup (shared with freeze).
    assert [(c, s) for c, s, _ in bank.fulfills] == [("account_info", "cards")]
    assert bank.mutating_calls() == []
    assert result["routing"]["action"] == "report_lost_card"
    assert result["payload"]["cardId"] == "41"
    assert result["payload"]["cardLast4"] == "0251"
    assert result["payload"]["executed"] is False


def test_report_lost_card_with_several_cards_asks_which(client, bank):
    bank.cards = [
        {"id": "41", "cardNumber": "4001230000000251"},
        {"id": "42", "cardNumber": "4001230000000999"},
    ]
    bank.routes["lost"] = BankingService("card_requests", "report_lost_card", None, {"reasonCode": "LOST"})
    events = _post(client, "I lost my card")
    assert _result(events)["type"] == "ACCOUNT_SELECTION_REQUIRED"
    assert bank.mutating_calls() == []


def test_report_lost_card_without_cards(client, bank):
    bank.cards = []
    bank.routes["lost"] = BankingService("card_requests", "report_lost_card", None, {})
    events = _post(client, "I lost my card")
    assert _token(events) == "You don't have any cards on file."
    assert _result(events)["payload"] == {"cards": []}
    assert bank.mutating_calls() == []


# --- profile photo: redirect only -------------------------------------------------


def test_profile_photo_redirects_without_bank_call(client, bank):
    bank.routes["photo"] = BankingService("profile_update", "update_profile_image", None, None)
    events = _post(client, "change my profile photo")
    result = _result(events)
    assert bank.fulfills == []
    assert result["type"] == "BANKING_SERVICE"
    assert result["routing"]["action"] == "update_profile_image"
    assert result["payload"] == {"executed": False}


# --- email / mobile: OTP flows ----------------------------------------------------


EMAIL_ROUTE = BankingService("profile_update", "update_email", None, {"newEmail": "New@Example.com"})
MOBILE_ROUTE = BankingService("profile_update", "update_mobile", None, {"newPhone": "+880 1898-765432"})


def _start_email(client, bank):
    bank.routes["email"] = EMAIL_ROUTE
    events = _post(client, "change my email")
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["verificationStatus"] == "OTP_SENT"
    assert result["payload"]["newEmail"] == "new@example.com"
    return events


def _start_mobile(client, bank):
    bank.routes["mobile"] = MOBILE_ROUTE
    events = _post(client, "change my mobile number")
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["newPhone"] == NEW_PHONE
    return events


def test_email_otp_goes_to_customers_own_phone(client, bank):
    _start_email(client, bank)
    assert bank.sends == [CUSTOMER_PHONE]
    assert bank.fulfills == []


def test_mobile_otp_goes_to_the_current_registered_phone(client, bank):
    events = _start_mobile(client, bank)
    # Bank binds the token to the CURRENT phone (UserAuthServiceImpl.updateMobile).
    assert bank.sends == [CUSTOMER_PHONE]
    assert NEW_PHONE in _token(events)
    assert bank.fulfills == []


def test_email_success_verifies_against_own_phone_and_executes(client, bank):
    _start_email(client, bank)
    events = _post(client, "submit", {"otp": "123456"})
    assert bank.verifies == [(CUSTOMER_PHONE, "123456")]
    assert bank.fulfills == [
        ("profile_update", "update_email", {"newEmail": "new@example.com", "verificationToken": "vtoken-1"}),
    ]
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE"
    assert result["payload"] == {"executed": True, "newEmail": "new@example.com"}
    assert "verificationToken" not in json.dumps(events)
    assert "vtoken-1" not in json.dumps(events)


def test_mobile_success_verifies_against_current_phone_and_executes(client, bank):
    _start_mobile(client, bank)
    events = _post(client, "submit", {"otp": "654321"})
    assert bank.verifies == [(CUSTOMER_PHONE, "654321")]
    assert bank.fulfills == [
        ("profile_update", "update_mobile", {"newPhone": NEW_PHONE, "verificationToken": "vtoken-1"}),
    ]
    assert _result(events)["payload"] == {"executed": True, "newPhone": NEW_PHONE}


@pytest.mark.parametrize("starter", [_start_email, _start_mobile])
def test_wrong_code_reports_attempts_and_does_not_execute(client, bank, starter):
    starter(client, bank)
    bank.verify_errors.append(AdapterValidationError("OTP_INCORRECT", "bad", attempts_remaining=2))
    events = _post(client, "submit", {"otp": "000000"})
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["verificationStatus"] == "OTP_INCORRECT"
    assert result["payload"]["attemptsRemaining"] == 2
    assert "2 attempts left" in _token(events)
    assert bank.fulfills == []
    assert len(bank.sends) == 1
    # Still pending: the right code then succeeds.
    events = _post(client, "submit", {"otp": "111111"})
    assert _result(events)["payload"]["executed"] is True
    assert len(bank.mutating_calls()) == 1


@pytest.mark.parametrize("starter,decline", [
    (_start_email, "Okay, I won't change your email address."),
    (_start_mobile, "Okay, I won't change your mobile number."),
])
def test_cancel_stops_without_verify_or_change(client, bank, starter, decline):
    starter(client, bank)
    events = _post(client, "cancel")
    assert _token(events) == decline
    assert _result(events)["payload"] == {"executed": False, "cancelled": True}
    assert bank.verifies == [] and bank.fulfills == []


@pytest.mark.parametrize("starter", [_start_email, _start_mobile])
def test_otp_typed_in_message_text_is_never_used(client, bank, starter):
    starter(client, bank)
    events = _post(client, "my code is 482916")
    result = _result(events)
    assert result["type"] == "OTP_REQUIRED"
    assert result["payload"]["verificationStatus"] == "CREDENTIALS_MISSING"
    assert bank.verifies == [] and bank.fulfills == []
    # Never sent to the classifier either.
    assert len(bank.classify_calls) == 1
    assert "482916" not in repr(session_module.get_session(CUSTOMER_PHONE))


def test_expired_code_resends_to_same_target(client, bank):
    _start_mobile(client, bank)
    bank.verify_errors.append(AdapterValidationError("OTP_EXPIRED", "expired"))
    events = _post(client, "submit", {"otp": "111111"})
    assert _result(events)["payload"]["verificationStatus"] == "OTP_RESENT"
    assert bank.sends == [CUSTOMER_PHONE, CUSTOMER_PHONE]
    assert bank.fulfills == []


def test_invalid_mobile_is_asked_again_and_no_sms_sent(client, bank):
    bank.routes["mobile"] = BankingService("profile_update", "update_mobile", None, {"newPhone": "12345"})
    events = _post(client, "change my mobile number")
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"
    assert bank.sends == []


def test_send_throttled_changes_nothing(client, bank):
    bank.send_errors.append(AdapterValidationError("SEND_THROTTLED", "slow down"))
    bank.routes["email"] = EMAIL_ROUTE
    events = _post(client, "change my email")
    assert _result(events)["payload"] == {"executed": False, "verificationStatus": "SEND_THROTTLED"}
    assert bank.fulfills == []


def test_change_failure_after_verified_otp_never_claims_success(client, bank, monkeypatch):
    _start_email(client, bank)

    async def failing(customer_identity, jwt, category, service, subservice, payload):
        raise AdapterUnavailableError("down")

    monkeypatch.setattr(chat_module, "fulfill_banking_service", failing)
    events = _post(client, "submit", {"otp": "123456"})
    assert _result(events)["type"] == "SERVICE_UNAVAILABLE"
    assert "nothing has been changed" in _token(events)
