"""Fixes from the 2026-10-03 live multi-turn eval: leaving a pending freeze OTP
step, no invented freeze reason, masking of bare digit runs, no-credit-card answer."""
import asyncio
import json

import pytest

import app.banking.routing as routing_module
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


_REAL_GROUND = chat._ground_freeze_request  # conftest patches it per test
_REAL_FILL = chat._llm_fill_pending_fields  # conftest patches it per test

# The live transfer menu (taxonomy key "subServices"): every transfer/fee id is read
# from here, never from a hardcoded list.
TRANSFER_TAXONOMY = {"categories": [{"id": "transfer", "services": [
    {"id": "bank_transfer", "name": "Bank Transfer", "subServices": [
        {"id": "own_account", "name": "Own Account Transfer"},
        {"id": "city_account", "name": "Polygon Bank Account Transfer"},
        {"id": "other_bank", "name": "Other Bank Transfer"}]},
    {"id": "wallet_transfer", "name": "Wallet Transfer", "subServices": [
        {"id": "bkash", "name": "bKash"}, {"id": "nagad", "name": "Nagad"}]},
    {"id": "cash_by_code", "name": "Cash by Code"},
]}]}


@pytest.fixture
def transfer_menu(monkeypatch):
    monkeypatch.setattr(routing_module, "get_taxonomy", lambda: TRANSFER_TAXONOMY)
    monkeypatch.setattr(chat, "get_taxonomy", lambda: TRANSFER_TAXONOMY)
    monkeypatch.setattr(chat, "fee_transaction_types", lambda: routing_module.fee_transaction_types(TRANSFER_TAXONOMY))
    return TRANSFER_TAXONOMY


def _freeze(payload):
    return BankingService("card_services", "frezz_unfrezz", None, payload)


def _facts(monkeypatch, reason, block, seen=None):
    async def fake(messages):
        if seen is not None:
            seen.extend(messages)
        return reason, block

    monkeypatch.setattr(chat, "_freeze_request_facts", fake)


def test_invented_reason_replaced_by_none_when_customer_only_asked_to_block(monkeypatch):
    _facts(monkeypatch, None, "freeze my card")
    result = asyncio.run(_REAL_GROUND(_freeze({"reason": "lost"}), "freeze my card", []))
    assert result.payload is None


def test_reason_is_the_customers_words_and_earlier_turns_are_read(monkeypatch):
    seen = []
    _facts(monkeypatch, "card was stolen", "block it", seen)
    turns = [ChatTurn(timestamp=None, message="card churi hoye gese", classification=None)]
    result = asyncio.run(_REAL_GROUND(_freeze({"reason": "lost", "cardId": "45"}), "block koro", turns))
    assert result.payload == {"reason": "card was stolen", "cardId": "45"}
    assert seen == ["card churi hoye gese", "block koro"]


def test_vague_card_problem_is_not_a_freeze(monkeypatch):
    _facts(monkeypatch, None, None)
    result = asyncio.run(_REAL_GROUND(_freeze({"reason": "lost"}), "reset my card pin", []))
    assert isinstance(result, chat.Clarification)
    assert "lost, stolen or misused" in result.question


def test_grounding_ignores_other_services(monkeypatch):
    async def boom(messages):
        raise AssertionError("must not be called")

    monkeypatch.setattr(chat, "_freeze_request_facts", boom)
    other = BankingService("account_info", "balance", None, {"reason": "x"})
    assert asyncio.run(_REAL_GROUND(other, "balance", [])) is other


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
    assert result.data == {"creditCard": None, "hasCreditCard": False}


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


def test_accounts_reply_view_uses_ledger_balance_and_counts_each_account_once():
    data = {"data": {
        "accounts": [{"accountNumber": "100126000056", "accountType": "SAVINGS", "balance": "0"}],
        "ledgerAccounts": [{"identifier": "100126000056", "balance": "9000000"},
                           {"identifier": "900000000001", "balance": "500"}],
    }}
    view = chat._accounts_for_prompt(data)
    assert view["data"]["accounts"] == [
        {"accountNumber": "100126000056", "accountType": "SAVINGS", "balance": "9000000"}]
    assert view["data"]["ledgerAccounts"] == [{"identifier": "900000000001", "balance": "500"}]
    assert data["data"]["accounts"][0]["balance"] == "0"  # frontend payload untouched


def test_grounded_drops_quotes_the_customer_never_wrote():
    assert chat._grounded("my card was stolen", "freeze my card") is None
    assert chat._grounded("card churi hoye gese", "card churi hoye gese, block koro") == "card churi hoye gese"
    assert chat._grounded("I lost my card", "i lost my card") == "I lost my card"
    assert chat._grounded(None, "x") is None


def test_echoed_correction_text_is_never_shown_to_the_customer():
    from app.banking.routing import _INVALID_PATH_CORRECTION, _echoes

    assert _echoes("That category/service/subservice doesn", _INVALID_PATH_CORRECTION)
    assert not _echoes("Which account's transactions would you like to see?", _INVALID_PATH_CORRECTION)


def test_poisha_named_keys_are_converted_to_taka():
    out = chat._redact_for_prompt({"products": [{"issuanceFeePoisha": 5788800, "name": "GOLD"}]})
    assert out["products"][0]["issuanceFeePoisha"] == "Tk 57,888.00"


def test_login_history_without_device_gathers_all_devices(monkeypatch):
    calls = []

    async def fake_call(method, path, jwt, **kw):
        calls.append(path)
        if path == "/auth/v1/devices":
            return [{"id": 1, "deviceId": "aaa"}, {"id": 2, "deviceId": "bbb"}]
        stamp = "2026-10-01" if "aaa" in path else "2026-10-02"
        return {"records": [{"loginAt": stamp, "status": "SUCCESS"}]}

    monkeypatch.setattr(real, "_call", fake_call)
    result = asyncio.run(real.LoginHistoryAdapter().fulfill(None, "jwt", "login_history", None))
    assert calls == ["/auth/v1/devices", "/auth/v1/devices/aaa/login-history", "/auth/v1/devices/bbb/login-history"]
    assert [r["loginAt"] for r in result.data["records"]] == ["2026-10-02", "2026-10-01"]


def test_wrong_category_for_a_unique_service_is_corrected(monkeypatch):
    from app.banking import routing

    taxonomy = {"categories": [
        {"id": "polygon_services", "services": [{"id": "transaction_history"}, {"id": "shared"}]},
        {"id": "account_info", "services": [{"id": "balance"}, {"id": "shared"}]},
    ]}
    monkeypatch.setattr(routing, "get_taxonomy", lambda: taxonomy)
    assert routing._only_category_of("transaction_history") == "polygon_services"
    assert routing._only_category_of("shared") is None
    assert routing._only_category_of("nope") is None


def test_running_balance_is_labelled_for_the_reply():
    view = chat._label_running_balances({"transactions": [{"amount": 500000, "balance": 9500000}], "balance": 1})
    assert view == {"transactions": [{"amount": 500000, "balanceAfterThisTransaction": 9500000}], "balance": 1}
    redacted = chat._redact_for_prompt(view, "transaction_history")
    assert redacted["transactions"][0]["balanceAfterThisTransaction"] == "Tk 95,000.00"


def test_fee_type_is_mapped_to_a_live_id_or_dropped(transfer_menu):
    def fee(t, message=""):
        return chat._normalize_fee_type(
            BankingService("fees", "fee_quote", None, {"transactionType": t, "amount": 500}), message)

    # Exactly a live id (case / spaces / hyphens normalised) -- no substring mapping.
    assert fee("bkash").payload == {"transactionType": "bkash", "amount": 500}
    assert fee("Other Bank").payload == {"transactionType": "other_bank", "amount": 500}
    assert fee("other-bank").payload == {"transactionType": "other_bank", "amount": 500}
    assert fee("bkash transfer").payload == {"amount": 500}
    assert fee("NPSB").payload == {"amount": 500}
    # A wallet must be one the customer actually named.
    assert fee("nagad", "fee for 500 to a mobile wallet").payload == {"amount": 500}
    assert fee("nagad", "nagad e 500 pathale fee koto").payload == {"transactionType": "nagad", "amount": 500}


def test_fee_type_is_kept_when_no_taxonomy_is_loaded(monkeypatch):
    monkeypatch.setattr(chat, "fee_transaction_types", lambda: [])
    out = chat._normalize_fee_type(BankingService("fees", "fee_quote", None, {"transactionType": "bkash"}))
    assert out.payload == {"transactionType": "bkash"}


def test_foreign_script_and_repeated_quote_guards():
    assert chat._foreign_script("কি বলছেন?", "taka kete nise")
    assert not chat._foreign_script("কি বলছেন?", "টাকা কেটে নিসে")
    assert not chat._foreign_script("What happened?", "taka kete nise")
    assert chat._quoted("lost it! lost it!") == "lost it!"


def test_dispute_summary_shows_only_the_account_ending():
    kind, facts, must = chat._dispute_summary_say(
        {"accountNumber": "100126000056", "transactionReferenceNo": "TXN1",
         "transactionSummary": "Tk 5.00 ATM debit on 2026-10-01", "remarks": "not received"})
    assert kind == "summary"
    assert must == {"account ending": "0056"}
    assert "100126000056" not in repr((facts, must))
    # the customer sees what the transaction was, never its raw reference id
    assert facts["transaction"] == "Tk 5.00 ATM debit on 2026-10-01"
    assert "TXN1" not in repr((facts, must))
    assert facts["their reason"] == "not received"
    assert facts["done in chat"].startswith("no")


def test_compact_for_prompt_drops_links_keeps_nulls_and_empty_lists():
    data = {"transactions": [{"amount": "Tk 5.00", "icon": "https://x/y.png", "note": None, "tags": []}],
            "pagination": {"hasNext": False}, "items": []}
    assert chat._compact_for_prompt(data) == {
        "transactions": [{"amount": "Tk 5.00", "note": None, "tags": []}], "transactions (total)": 1,
        "pagination": {"hasNext": False}, "items": []}


def test_compact_for_prompt_states_the_total_of_nested_record_lists():
    """The model never counts rows itself: a customer with one account holding one card
    was told "two" and "three accounts" before every list carried its total."""
    data = {"accounts": [{"name": "a", "cards": [{"id": 1}, {"id": 2}]}]}
    out = chat._compact_for_prompt(data)
    assert out["accounts (total)"] == 1
    assert out["accounts"][0]["cards (total)"] == 2


_REAL_STREAM = chat._stream_reply  # conftest swaps it for the non-streamed path


class _FakeStream:
    def __init__(self, pieces):
        self._lines = [json.dumps({"message": {"content": p}, "done": False}) for p in pieces]
        self._lines.append(json.dumps({"message": {"content": ""}, "done": True}))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _stream_with(monkeypatch, pieces):
    monkeypatch.setattr(real.httpx.AsyncClient, "stream", lambda self, *a, **k: _FakeStream(pieces))


def _collect(gen):
    async def run():
        return [piece async for piece in gen]
    return asyncio.run(run())


def test_stream_releases_whole_verified_sentences(monkeypatch):
    _stream_with(monkeypatch, ["Your balance is Tk 90", ",000", ".00. ", "It is ", "available now."])
    out = _collect(_REAL_STREAM("balance?", "balance", None, {"balance": 9000000}))
    assert out == ["Your balance is Tk 90,000.00.", " It is available now."]


def test_stream_stops_before_an_unsupported_number_and_finishes_with_facts(monkeypatch):
    _stream_with(monkeypatch, ["Here is your balance. ", "It is Tk 31,000.00", " today."])
    out = "".join(_collect(_REAL_STREAM("balance?", "balance", None, {"balance": 9000000})))
    assert "31,000" not in out
    # the verified sentence, then the data itself as plain facts (no prose template)
    assert out == "Here is your balance. balance: Tk 90,000.00"


def test_stream_with_bad_first_number_uses_the_non_streamed_path(monkeypatch):
    _stream_with(monkeypatch, ["Tk 31,000.00 is your balance."])

    async def fake_synth(message, service, subservice, data):
        return "checked reply"

    monkeypatch.setattr(chat, "_synthesize_reply", fake_synth)
    assert _collect(_REAL_STREAM("balance?", "balance", None, {"balance": 9000000})) == ["checked reply"]


def test_fee_quote_routing_offers_the_matching_transfer(transfer_menu):
    routing = chat._service_routing("fees", "fee_quote", None, {"transactionType": "nagad", "amount": 500})
    assert routing["action"] == "start_transfer"
    assert routing["transfer"] == {"category": "transfer", "service": "wallet_transfer",
                                   "subservice": "nagad", "prefill": {"amount": 500}}
    assert chat._service_routing("fees", "fee_quote", None, {"transactionType": "cash_by_code"})["action"] == "redirect"
    assert chat._service_routing("account_info", "balance", None, None)["action"] == "redirect"
    bank = chat._service_routing("fees", "fee_quote", None, {"transactionType": "other_bank", "amount": 900})
    assert bank["transfer"]["service"] == "bank_transfer" and bank["transfer"]["subservice"] == "other_bank"
    # an id the live menu doesn't list never starts a transfer
    assert chat._service_routing("fees", "fee_quote", None, {"transactionType": "upay"})["action"] == "redirect"


def _fee_pending(payload=None):
    return [ChatTurn(timestamp=None, message="fees", classification={
        "type": "CLARIFICATION_REQUIRED", "category": "fees", "service": "fee_quote",
        "payload": payload or {}, "missingFields": ["transactionType", "amount"]})]


def _model_fills(monkeypatch, obj):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": json.dumps(obj)}

    async def fake_post(self, url, *args, **kwargs):
        return _Resp()

    monkeypatch.setattr(real.httpx.AsyncClient, "post", fake_post)


def test_transfer_shaped_answer_to_a_fee_question_is_the_fee(monkeypatch, transfer_menu):
    # Pending fee question: the reply fills the fee's own fields (slot filling), it
    # never becomes a transfer.
    _model_fills(monkeypatch, {"transactionType": "bkash", "amount": 500})
    out = asyncio.run(_REAL_FILL(_fee_pending(), "mobile wallet 500 taka"))
    # "bkash" was never said -> not assumed; the type is asked for next.
    assert (out.category, out.service, out.payload) == ("fees", "fee_quote", {"amount": 500})
    named = asyncio.run(_REAL_FILL(_fee_pending(), "bkash e 500"))
    assert (named.category, named.service) == ("fees", "fee_quote")
    assert named.payload == {"transactionType": "bkash", "amount": 500}


def test_transfer_wording_without_a_pending_fee_question_stays_a_transfer(monkeypatch, transfer_menu):
    calls = []

    async def fake_post(self, url, *args, **kwargs):
        calls.append(url)
        raise AssertionError("no slot filling without a pending question")

    monkeypatch.setattr(real.httpx.AsyncClient, "post", fake_post)
    assert asyncio.run(_REAL_FILL([], "i want to transfer money to bkash")) is None
    assert calls == []


def test_send_after_fee_hint_targets_the_quoted_transfer_from_the_taxonomy(transfer_menu):
    hint = routing_module._send_after_fee_hint(
        {"category": "fees", "service": "fee_quote", "request": {"transactionType": "nagad", "amount": 500}})
    assert 'category="transfer", service="wallet_transfer", subservice="nagad"' in hint
    assert 'payload={"amount": 500}' in hint
    bank = routing_module._send_after_fee_hint(
        {"category": "fees", "service": "fee_quote", "request": {"transactionType": "own_account"}})
    assert 'service="bank_transfer", subservice="own_account"' in bank
    assert "payload" not in bank


@pytest.mark.parametrize("previous", [
    {"category": "fees", "service": "fee_quote", "request": {"transactionType": "upay", "amount": 5}},
    {"category": "fees", "service": "fee_quote", "request": {"transactionType": "cash_by_code"}},
    {"category": "fees", "service": "fee_quote", "request": {}},
    {"category": "account_info", "service": "balance", "request": {"transactionType": "bkash"}},
])
def test_send_after_fee_hint_is_empty_without_a_live_transfer_target(transfer_menu, previous):
    # "upay" isn't in this taxonomy: no hardcoded wallet list fills the gap.
    assert routing_module._send_after_fee_hint(previous) == ""


def test_subservice_ids_reads_the_live_taxonomy(transfer_menu):
    assert routing_module._subservice_ids("transfer", "wallet_transfer") == ["bkash", "nagad"]
    assert routing_module._subservice_ids("transfer", "cash_by_code") == []
    assert routing_module._subservice_ids("nope", "wallet_transfer") == []
    assert chat._subservice_ids is routing_module._subservice_ids


# --- data answers use /api/chat and the composer's checks (T-77) -------------------


def _chat_replies(monkeypatch, *texts):
    sent = []
    queue = list(texts)

    class _R:
        def __init__(self, text):
            self._text = text

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": self._text}}

    async def fake_post(self, url, *args, **kwargs):
        sent.append((url, kwargs["json"]))
        return _R(queue.pop(0))

    monkeypatch.setattr(real.httpx.AsyncClient, "post", fake_post)
    return sent


def test_synthesize_reply_retries_a_markdown_reply_then_sends_the_checked_one(monkeypatch):
    sent = _chat_replies(monkeypatch, "- Your balance is Tk 90,000.00", "Your balance is Tk 90,000.00.")
    out = asyncio.run(chat._synthesize_reply("balance?", "balance", None, {"balance": 9000000}))
    assert out == "Your balance is Tk 90,000.00."
    assert len(sent) == 2 and all(url.endswith("/api/chat") for url, _ in sent)
    assert sent[1][1]["options"]["temperature"] == 0.0


def test_synthesize_reply_never_sends_a_foreign_currency_or_wrong_number(monkeypatch):
    _chat_replies(monkeypatch, "Your balance is €900.", "Your balance is Tk 31,000.00.")
    out = asyncio.run(chat._synthesize_reply("balance?", "balance", None, {"balance": 9000000}))
    assert "€" not in out and "31,000" not in out
    assert out == "balance: Tk 90,000.00"  # plain facts, no prose


def test_stream_posts_the_persona_as_a_system_message_to_api_chat(monkeypatch):
    seen = []

    def fake_stream(self, method, url, **kwargs):
        seen.append((url, kwargs["json"]))
        return _FakeStream(["Your balance is Tk 90,000.00."])

    monkeypatch.setattr(real.httpx.AsyncClient, "stream", fake_stream)
    out = _collect(_REAL_STREAM("balance?", "balance", None, {"balance": 9000000}))
    assert out == ["Your balance is Tk 90,000.00."]
    url, body = seen[0]
    assert url.endswith("/api/chat")
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
