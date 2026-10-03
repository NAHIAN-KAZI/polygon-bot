"""Fixes from the 2026-10-03 live multi-turn eval: leaving a pending freeze OTP
step, no invented freeze reason, masking of bare digit runs, no-credit-card answer."""
import asyncio

import pytest

import app.routes.chat as chat
from app.banking.adapters import real
from app.banking.routing import BankingService
from app.banking.session import ChatTurn


@pytest.mark.parametrize("message", ["4821", "123456", "Secret@123", "  0000  ", "my code is 0000 and pin 123456"])
def test_typed_codes_and_passwords_look_like_secrets(message):
    assert chat._looks_like_typed_secret(message)


@pytest.mark.parametrize(
    "message", ["nevermind, how much money do i have", "balance", "500", "u r useless", "ok"]
)
def test_ordinary_messages_do_not_look_like_secrets(message):
    assert not chat._looks_like_typed_secret(message)


def _freeze(payload):
    return BankingService("card_services", "frezz_unfrezz", None, payload)


def test_unstated_freeze_reason_is_dropped(monkeypatch):
    async def not_stated(messages, reason):
        assert messages == ["freeze my card"]
        return False

    monkeypatch.setattr(chat, "_reason_was_stated", not_stated)
    result = asyncio.run(chat._drop_unstated_freeze_reason(_freeze({"reason": "lost"}), "freeze my card", []))
    assert result.payload is None


def test_stated_freeze_reason_is_kept_and_earlier_turns_are_checked(monkeypatch):
    seen = {}

    async def stated(messages, reason):
        seen["messages"] = messages
        return True

    monkeypatch.setattr(chat, "_reason_was_stated", stated)
    turns = [ChatTurn(timestamp=None, message="someone stole my wallet", classification=None)]
    result = asyncio.run(chat._drop_unstated_freeze_reason(
        _freeze({"reason": "stolen", "cardId": "45"}), "block my card", turns))
    assert result.payload == {"reason": "stolen", "cardId": "45"}
    assert seen["messages"] == ["someone stole my wallet", "block my card"]


def test_reason_check_ignores_other_services(monkeypatch):
    async def boom(messages, reason):
        raise AssertionError("must not be called")

    monkeypatch.setattr(chat, "_reason_was_stated", boom)
    other = BankingService("account_info", "balance", None, {"reason": "x"})
    assert asyncio.run(chat._drop_unstated_freeze_reason(other, "balance", [])) is other


def test_redact_masks_linked_account_and_drops_identity_numbers():
    out = chat._redact_for_prompt({
        "cards": [{"linkedAccountNumber": "100126000056", "id": "45"}],
        "cif": "109260000178", "nid": "1234567890", "username": "taslim_islamic",
    })
    assert out["cards"][0]["linkedAccountNumber"] == "••••••••0056"
    assert out["cards"][0]["id"] == "45"
    assert "cif" not in out and "nid" not in out
    assert out["username"] == "taslim_islamic"



@pytest.mark.parametrize("adapter", [real.CreditCardSummaryAdapter(), real.CreditCardStatementAdapter()])
def test_no_credit_card_is_an_answer_not_an_outage(monkeypatch, adapter):
    async def fake_call(method, path, jwt, **kw):
        assert path == "/card/v1/cards"
        return {"data": [{"id": "45", "cardCategory": "DEBIT", "cardNumber": "4001000000000293"}]}

    monkeypatch.setattr(real, "_call", fake_call)
    result = asyncio.run(adapter.fulfill(None, "jwt", "x", None))
    assert result.data == {"creditCards": [], "hasCreditCard": False}


def test_coerce_payload_drops_empty_values_the_model_fills_in():
    from app.banking.routing import _coerce_payload

    assert _coerce_payload({"cardId": "", "isBilled": "", "month": ""}) is None
    assert _coerce_payload({"amount": 500, "walletNumber": " ", "note": None}) == {"amount": 500}
    assert _coerce_payload('{"month": "2026-10", "isBilled": ""}') == {"month": "2026-10"}


def test_number_moved_to_another_label_is_rejected():
    facts = "I've sent a code to your registered phone number. To freeze your debit card ending 0293, enter it."
    assert chat._number_keeps_its_label("0293", facts, "Code sent. To freeze your card ending 0293, enter it.")
    assert not chat._number_keeps_its_label(
        "0293", facts, "I've sent a code to your registered phone number 0293. To freeze this card, enter it.")
    assert chat._number_keeps_its_label("1,000.00", "Your balance is Tk 1,000.00.", "You have Tk 1,000.00 left.")


@pytest.mark.parametrize("bad_id", ["../../auth/v1/admin", "45/../../x", "45?x=1", "45#x", "4%2F5", "45 6"])
def test_payload_ids_cannot_inject_into_request_paths(monkeypatch, bad_id):
    sent = []

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, *a, **k):
            sent.append(a)

    monkeypatch.setattr(real.httpx, "AsyncClient", Client)
    with pytest.raises(real.AdapterUnavailableError, match="unsafe request path"):
        asyncio.run(real.CreditCardSummaryAdapter().fulfill(None, "jwt", "x", {"cardId": bad_id}))
    assert sent == []


def test_normal_paths_still_allowed():
    assert real._SAFE_PATH_RE.fullmatch("/card/v1/cards/45/credit-summary")
    assert real._SAFE_PATH_RE.fullmatch("/transfer/v1/my-limit/100126000056")
