"""T-65 poisha->taka, T-67 account-selection resumption, T-68 fact-preserving rewording."""
import asyncio
import json
from datetime import datetime, timezone

import pytest

import app.routes.chat as chat
from app.banking.routing import BankingService
from app.banking.session import ChatTurn

# conftest patches _phrase to identity per test; capture the real one at import time.
_REAL_PHRASE = chat._phrase


def test_format_poisha_converts_to_taka_with_two_decimals():
    assert chat._format_poisha(100228196915) == "৳1,002,281,969.15"
    assert chat._format_poisha("50000") == "৳500.00"
    assert chat._format_poisha(None) is None


def test_redact_for_prompt_converts_known_money_keys_and_drops_formatted():
    data = {"balance": 100000, "balanceFormatted": "৳1,000", "fees": {"charge": 2500, "vat": 0},
            "weekly": {"used": 791100, "current": None}, "pagination": {"totalCount": 3}}
    out = chat._redact_for_prompt(data, "transfer_limit")
    assert out["balance"] == "Tk 1,000.00"
    assert "balanceFormatted" not in out
    assert out["fees"] == {"charge": "Tk 25.00", "vat": "Tk 0.00"}
    assert out["weekly"] == {"used": "Tk 7,911.00", "current": None}
    assert out["pagination"] == {"totalCount": 3}
    assert data["balance"] == 100000  # original untouched


def test_redact_for_prompt_qr_history_amounts_are_already_taka():
    out = chat._redact_for_prompt({"data": [{"amount": "500.00"}]}, "qr_payment_history")
    assert out["data"][0]["amount"] == "Tk 500.00"


def test_enrich_payload_formatted_balance_is_taka_not_poisha():
    enriched = chat._enrich_payload("balance", None, {"balance": 100228196915})
    assert enriched["balanceFormatted"] == "৳1,002,281,969.15"


def _selection_turn(candidates, category="account_info", service="balance", payload=None):
    return ChatTurn(
        timestamp=datetime.now(timezone.utc), message="what's my balance",
        classification={"type": "ACCOUNT_SELECTION_REQUIRED", "category": category,
                         "service": service, "subservice": None, "question": "which one?",
                         "candidates": candidates, "payload": payload or {}},
    )


_ACCOUNTS = [
    {"accountNumber": "100126000015", "accountType": "SAVINGS"},
    {"accountNumber": "4100200000000379", "accountType": "CREDIT"},
]


def test_selection_by_last_digits_resumes_original_service():
    result = asyncio.run(chat._try_account_selection_completion(
        [_selection_turn(_ACCOUNTS)], "the one ending 0379", None))
    assert result == BankingService("account_info", "balance", None,
                                    {"accountNumber": "4100200000000379"})


def test_selection_by_frontend_picker_id():
    result = asyncio.run(chat._try_account_selection_completion(
        [_selection_turn(_ACCOUNTS)], "Selected", {"accountNumber": "100126000015"}))
    assert result.payload == {"accountNumber": "100126000015"}


def test_selection_by_wording_goes_to_llm_pick(monkeypatch):
    async def pick(message, candidates):
        assert message == "my savings one"
        return 0

    monkeypatch.setattr(chat, "_llm_pick_candidate", pick)
    result = asyncio.run(chat._try_account_selection_completion(
        [_selection_turn(_ACCOUNTS)], "my savings one", None))
    assert result.payload == {"accountNumber": "100126000015"}


def test_selection_none_when_reply_is_a_new_question(monkeypatch):
    async def pick(message, candidates):
        return None

    monkeypatch.setattr(chat, "_llm_pick_candidate", pick)
    assert asyncio.run(chat._try_account_selection_completion(
        [_selection_turn(_ACCOUNTS)], "how many accounts do i have", None)) is None


def test_selection_card_candidate_yields_card_id_and_keeps_original_payload():
    cards = [{"id": "41", "cardNumber": "4001****0251", "cardType": "DEBIT"},
             {"id": "46", "cardNumber": "4001****0301", "cardType": "DEBIT"}]
    result = asyncio.run(chat._try_account_selection_completion(
        [_selection_turn(cards, "card_services", "frezz_unfrezz", {"reason": "lost"})],
        "0301", None))
    assert result.payload == {"reason": "lost", "cardId": "46", "cardLast4": "0301"}


def test_selection_reply_says_cards_for_card_lists():
    text = chat._account_selection_reply([{"id": "41", "cardNumber": "4001****0251", "cardType": "DEBIT"}])
    assert "multiple cards" in text


class _FakeResp:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._text}


@pytest.fixture
def real_phrase():
    return _REAL_PHRASE


def _patch_llm(monkeypatch, module, text):
    async def fake_post(self, *args, **kwargs):
        return _FakeResp(text)

    monkeypatch.setattr(module.httpx.AsyncClient, "post", fake_post)


def test_phrase_keeps_llm_wording_when_all_facts_survive(monkeypatch, real_phrase):
    _patch_llm(monkeypatch, chat, "Sure! Your card ending 0251 is now frozen.")
    out = asyncio.run(real_phrase("Your card ending 0251 has been frozen.", "freeze it"))
    assert out == "Sure! Your card ending 0251 is now frozen."


@pytest.mark.parametrize("bad", [
    "Your card is frozen.", "Your card ending 0251 cost $5.", "",
    "We texted your phone 0251. Your card ending 0251 has been frozen.",
])
def test_phrase_falls_back_to_facts_when_a_fact_is_lost_or_currency_is_wrong(monkeypatch, real_phrase, bad):
    _patch_llm(monkeypatch, chat, bad)
    facts = "Your card ending 0251 has been frozen."
    assert asyncio.run(real_phrase(facts, "freeze it")) == facts


def test_unsupported_numbers_flags_a_digit_the_data_does_not_contain():
    data = '{"balance": "Tk 1,002,281,969.15"}'
    assert chat._unsupported_numbers("Your balance is Tk 1,002,281,969.15.", data) == []
    assert chat._unsupported_numbers("Your balance is Tk 31,002,281,969.15.", data) == ["31,002,281,969.15"]


def test_redact_for_prompt_redacts_cif():
    assert "cif" not in chat._redact_for_prompt({"cif": "109260000178"})
