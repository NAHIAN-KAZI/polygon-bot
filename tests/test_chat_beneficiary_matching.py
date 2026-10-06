"""Tests for beneficiary name-matching + destination routing (TASKS.md T-39).

Covers the pure helper functions added to app/routes/chat.py --
_match_beneficiaries, _resolve_beneficiary_destination, the reply-builders,
and _trim_beneficiary -- plus the new branch in _chat_stream's BankingService
success path (service == "beneficiary" with payload.nameQuery/beneficiaryId)
end-to-end via /chat's SSE response, following the same
classify/verify_jwt/fulfill_banking_service monkeypatch style as
test_chat_banking_flow.py.
"""
import json

import app.routes.chat as chat_module
from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService

from tests.conftest import AUTH_HEADERS

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


def _install_session_fakes(monkeypatch):
    monkeypatch.setattr(chat_module, "get_classification_context", lambda customer_id: [])

    def _record_turn(*args, **kwargs):
        pass

    monkeypatch.setattr(chat_module, "record_turn", _record_turn)


def _install_audit_spy(monkeypatch):
    calls = []

    def _log(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(chat_module.audit, "log_banking_turn", _log)
    return calls


ASHAN = {
    "id": "ben-1",
    "nickname": "Ashan",
    "accountHolderName": "Md Ashan Ullah",
    "serviceType": "OWN_BANK",
}
ASHANUR = {
    "id": "ben-2",
    "nickname": None,
    "accountHolderName": "Ashanur Rahman",
    "serviceType": "OTHER_BANK",
}
BIKASH_MOM = {
    "id": "ben-3",
    "nickname": "Mom",
    "accountHolderName": "Rahima Begum",
    "serviceType": "MFS",
    "mfsProvider": "Bkash",
}


# --- _match_beneficiaries ----------------------------------------------------


def test_match_exact_nickname_match():
    result = chat_module._match_beneficiaries("Ashan", [ASHAN, BIKASH_MOM])
    assert result == [ASHAN]


def test_match_exact_account_holder_name_match():
    beneficiary = {"id": "x", "nickname": None, "accountHolderName": "John Smith"}
    result = chat_module._match_beneficiaries("John Smith", [beneficiary])
    assert result == [beneficiary]


def test_match_is_case_insensitive():
    result = chat_module._match_beneficiaries("aSHAN", [ASHAN])
    assert result == [ASHAN]


def test_match_prefers_substring_over_fuzzy():
    # "Ash" is a prefix/substring of both ASHAN's nickname and ASHANUR's
    # accountHolderName -- both should come back as substring matches,
    # without falling into the fuzzy path.
    result = chat_module._match_beneficiaries("Ash", [ASHAN, ASHANUR])
    assert {b["id"] for b in result} == {"ben-1", "ben-2"}


def test_match_fuzzy_fallback_triggers_only_without_substring_match():
    # "Ashn" is not a substring/prefix of "Ashan" but is close enough for
    # difflib.get_close_matches at cutoff=0.6.
    result = chat_module._match_beneficiaries("Ashn", [ASHAN])
    assert result == [ASHAN]


def test_match_fuzzy_fallback_does_not_trigger_when_substring_match_exists():
    close_but_irrelevant = {"id": "ben-9", "nickname": "Ash", "accountHolderName": None}
    # "Ashan" substring-matches ASHAN directly; the fuzzy pool (built only
    # from non-substring-matched entries) should never even be consulted.
    result = chat_module._match_beneficiaries("Ashan", [ASHAN, close_but_irrelevant])
    assert result == [ASHAN]


def test_match_multiple_substring_matches_returned():
    beneficiaries = [
        {"id": "1", "nickname": "Karim", "accountHolderName": None},
        {"id": "2", "nickname": None, "accountHolderName": "Abdul Karim"},
    ]
    result = chat_module._match_beneficiaries("karim", beneficiaries)
    assert {b["id"] for b in result} == {"1", "2"}


def test_match_empty_query_returns_empty_list():
    assert chat_module._match_beneficiaries("", [ASHAN]) == []


def test_match_blank_query_returns_empty_list():
    assert chat_module._match_beneficiaries("   ", [ASHAN]) == []


def test_match_no_beneficiaries_returns_empty_list():
    assert chat_module._match_beneficiaries("Ashan", []) == []


def test_match_non_list_beneficiaries_returns_empty_list():
    assert chat_module._match_beneficiaries("Ashan", "not-a-list") == []


def test_match_skips_non_dict_entries():
    result = chat_module._match_beneficiaries("Ashan", ["not-a-dict", ASHAN, 123, None])
    assert result == [ASHAN]


def test_match_skips_entries_missing_both_name_fields():
    no_names = {"id": "ben-x", "nickname": None, "accountHolderName": None}
    result = chat_module._match_beneficiaries("Ashan", [no_names, ASHAN])
    assert result == [ASHAN]
    # and querying for something that would only match the nameless entry
    # (impossible, since it has no names) returns empty rather than crashing
    assert chat_module._match_beneficiaries("anything", [no_names]) == []


# --- _resolve_beneficiary_destination ---------------------------------------


def test_resolve_destination_own_bank():
    assert chat_module._resolve_beneficiary_destination({"serviceType": "OWN_BANK"}) == {
        "action": "own_bank_transfer"
    }


def test_resolve_destination_other_bank():
    assert chat_module._resolve_beneficiary_destination({"serviceType": "OTHER_BANK"}) == {
        "action": "other_bank_transfer"
    }


def test_resolve_destination_mfs_with_provider_lowercases_provider():
    result = chat_module._resolve_beneficiary_destination({"serviceType": "MFS", "mfsProvider": "Bkash"})
    assert result == {"action": "wallet_transfer", "provider": "bkash"}


def test_resolve_destination_mfs_without_provider_returns_none():
    assert chat_module._resolve_beneficiary_destination({"serviceType": "MFS", "mfsProvider": None}) is None
    assert chat_module._resolve_beneficiary_destination({"serviceType": "MFS"}) is None


def test_resolve_destination_unknown_service_type_returns_none():
    assert chat_module._resolve_beneficiary_destination({"serviceType": "CARD_PAYMENT"}) is None
    assert chat_module._resolve_beneficiary_destination({}) is None


# --- _beneficiary_name / _trim_beneficiary ----------------------------------


def test_display_name_prefers_nickname():
    assert chat_module._beneficiary_name(ASHAN) == "Ashan"


def test_display_name_falls_back_to_account_holder_name():
    assert chat_module._beneficiary_name(ASHANUR) == "Ashanur Rahman"


def test_display_name_none_when_both_missing():
    # No invented generic name: the composer simply gets no name fact.
    assert chat_module._beneficiary_name({}) is None


def test_trim_beneficiary_keeps_only_expected_keys():
    beneficiary = {
        "id": "ben-1",
        "nickname": "Ashan",
        "accountHolderName": "Md Ashan Ullah",
        "serviceType": "OWN_BANK",
        "mfsProvider": None,
        "accountNumber": "12345",
        "bankName": "Polygon Bank",
        "photoUrl": "http://example.com/x.png",
    }
    result = chat_module._trim_beneficiary(beneficiary)
    assert result == {
        "id": "ben-1",
        "nickname": "Ashan",
        "accountHolderName": "Md Ashan Ullah",
        "serviceType": "OWN_BANK",
        "mfsProvider": None,
    }
    assert set(result.keys()) == {"id", "nickname", "accountHolderName", "serviceType", "mfsProvider"}


# --- end-to-end /chat SSE flow ----------------------------------------------


def _install_beneficiary_fixture(monkeypatch, beneficiaries, message="send money to Ashan", payload=None):
    async def fake_classify(message, recent_turns=None):
        return BankingService(
            category="polygon_services",
            service="beneficiary",
            subservice=None,
            payload=payload or {"nameQuery": "Ashan"},
        )

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"beneficiaries": beneficiaries})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    return message


def test_e2e_name_query_single_match_returns_beneficiary_match(client, monkeypatch):
    message = _install_beneficiary_fixture(monkeypatch, [ASHAN, BIKASH_MOM], payload={"nameQuery": "Ashan"})
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": message}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [name for name, _ in events] == ["token", "result", "done"]

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("redirect:")
    assert "beneficiary: Ashan" in token_event["token"]
    assert "pre-filled" in token_event["token"]  # a routable destination opens the transfer screen

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BENEFICIARY_MATCH"
    assert result_event["category"] == "polygon_services"
    assert result_event["service"] == "beneficiary"
    assert result_event["payload"] == {
        "beneficiary": ASHAN,
        "destination": {"action": "own_bank_transfer"},
    }
    assert result_event["routing"] == {
        "category": "polygon_services",
        "service": "beneficiary",
        "subservice": None,
        "action": "own_bank_transfer",
    }

    assert len(audit_spy) == 1
    _, kwargs = audit_spy[0]
    assert "payload" not in kwargs


def test_e2e_name_query_zero_matches_returns_clarification_required(client, monkeypatch):
    message = _install_beneficiary_fixture(
        monkeypatch, [ASHANUR, BIKASH_MOM], message="send money to Zubair", payload={"nameQuery": "Zubair"}
    )

    resp = client.post("/chat", json={"message": message}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    token_event = next(data for name, data in events if name == "token")
    assert token_event["token"].startswith("ask:")
    assert "name searched: Zubair" in token_event["token"]
    assert "no saved beneficiary has that name" in token_event["token"]

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "CLARIFICATION_REQUIRED"
    assert result_event["category"] is None
    assert result_event["service"] is None
    assert result_event["subservice"] is None
    assert result_event["payload"] is None


def test_e2e_name_query_zero_matches_audit_includes_question(client, monkeypatch):
    message = _install_beneficiary_fixture(
        monkeypatch, [ASHANUR, BIKASH_MOM], message="send money to Zubair", payload={"nameQuery": "Zubair"}
    )
    audit_spy = _install_audit_spy(monkeypatch)

    resp = client.post("/chat", json={"message": message}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    assert len(audit_spy) == 1
    args, kwargs = audit_spy[0]
    _, turn_classification = args
    assert turn_classification["type"] == "CLARIFICATION_REQUIRED"
    assert turn_classification["question"].startswith("ask:")
    assert "name searched: Zubair" in turn_classification["question"]


def test_e2e_name_query_multiple_matches_returns_beneficiary_selection_required(client, monkeypatch):
    message = _install_beneficiary_fixture(
        monkeypatch, [ASHAN, ASHANUR], message="send money to Ash", payload={"nameQuery": "Ash"}
    )

    resp = client.post("/chat", json={"message": message}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BENEFICIARY_SELECTION_REQUIRED"
    assert result_event["category"] == "polygon_services"
    assert result_event["service"] == "beneficiary"
    trimmed_ids = {b["id"] for b in result_event["payload"]["beneficiaries"]}
    assert trimmed_ids == {"ben-1", "ben-2"}
    for trimmed in result_event["payload"]["beneficiaries"]:
        assert set(trimmed.keys()) == {"id", "nickname", "accountHolderName", "serviceType", "mfsProvider"}

    # the question names every matching beneficiary
    token = next(data for name, data in events if name == "token")["token"]
    assert token.startswith("choose:")
    assert "Ashan" in token and "Ashanur Rahman" in token


def test_e2e_beneficiary_id_resubmit_resolves_directly_skipping_name_matching(client, monkeypatch):
    # nameQuery is present but wouldn't have matched anything -- beneficiaryId
    # must still win per the source's `if beneficiary_id is not None` check.
    message = _install_beneficiary_fixture(
        monkeypatch,
        [ASHAN, ASHANUR, BIKASH_MOM],
        message="the second one",
        payload={"nameQuery": "totally-nonmatching-name", "beneficiaryId": "ben-3"},
    )

    resp = client.post("/chat", json={"message": message}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BENEFICIARY_MATCH"
    assert result_event["payload"]["beneficiary"] == BIKASH_MOM
    assert result_event["payload"]["destination"] == {"action": "wallet_transfer", "provider": "bkash"}
    assert result_event["routing"]["action"] == "wallet_transfer"
    token = next(data for name, data in events if name == "token")["token"]
    assert "beneficiary: Mom" in token


def test_e2e_non_beneficiary_banking_service_flow_unaffected(client, monkeypatch):
    async def fake_classify(message, recent_turns=None):
        return BankingService(category="account_info", service="balance", subservice="balance")

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER_ID)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        return AdapterResult(data={"balance": "500.00"})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    _install_session_fakes(monkeypatch)

    resp = client.post("/chat", json={"message": "what's my balance"}, headers=JWT_HEADERS)

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    result_event = next(data for name, data in events if name == "result")
    assert result_event["type"] == "BANKING_SERVICE"
    assert result_event["payload"] == {"balance": "500.00", "balanceFormatted": "৳5.00"}  # bank balances are poisha (T-65)
