"""Transfer understanding fixes found by the live probe: a tool call the model wrote as text (with
the closing brace missing) is recovered, and the number the customer typed reaches the extractor."""
import asyncio
import json

import httpx

import app.banking.routing as routing_module
import app.routes.chat as chat_module

_REAL_FILL = chat_module._fill_fields
# the real follow-up filler: conftest swaps the module attribute for a stand-in
from tests.test_chat_banking_flow import _real_fill_pending_fields as _REAL_FILL_PENDING  # noqa: E402


# --- _tool_call_from_text ----------------------------------------------------------------------


def test_a_tool_call_written_as_text_with_a_missing_closing_brace_is_recovered():
    text = ('{"name": "route_banking_service", "parameters": {"category": "transfer", '
            '"service": "wallet_transfer", "subservice": "bkash", "payload": {"amount": "12500"}}')
    calls = routing_module._tool_call_from_text(text)
    assert calls == [{"function": {"name": "route_banking_service", "arguments": {
        "category": "transfer", "service": "wallet_transfer", "subservice": "bkash",
        "payload": {"amount": "12500"}}}}]


def test_a_complete_call_and_the_arguments_key_both_work():
    assert routing_module._tool_call_from_text('{"name": "answer_kb_question", "arguments": {}}')[0]["function"]["name"] == "answer_kb_question"
    assert routing_module._tool_call_from_text('{"name": "ask_clarification", "parameters": {"question": "which?"}}')[0]["function"]["arguments"] == {"question": "which?"}


def test_a_brace_inside_a_string_does_not_confuse_the_repair():
    calls = routing_module._tool_call_from_text('{"name": "route_banking_service", "parameters": {"note": "a}b"}')
    assert calls[0]["function"]["arguments"] == {"note": "a}b"}


def test_text_that_is_not_one_of_our_tool_calls_is_not_a_tool_call():
    for text in (None, "", "hello there", '{"name": "delete_everything", "parameters": {}}', "[1, 2]", '{"x": 1}', '{"name": "route_banking_service", "parameters": {"a": '):
        assert routing_module._tool_call_from_text(text) == []


def test_post_classification_uses_the_recovered_call_when_ollama_returns_no_tool_call(monkeypatch):
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": '{"name": "route_banking_service", "parameters": {"category": "transfer", "service": "wallet_transfer", "subservice": "nagad", "payload": {"amount": "1250"}}'}}

    async def fake_post(self, *a, **k):
        return Resp()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    calls = asyncio.run(routing_module._post_classification([{"role": "user", "content": "x"}]))
    assert calls[0]["function"]["arguments"]["subservice"] == "nagad"


def test_a_real_tool_call_is_used_as_is(monkeypatch):
    real = [{"function": {"name": "route_banking_service", "arguments": {"category": "fees", "service": "fee_quote"}}}]

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"tool_calls": real, "content": ""}}

    async def fake_post(self, *a, **k):
        return Resp()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert asyncio.run(routing_module._post_classification([])) == real


# --- the extractor sees the number the customer typed -------------------------------------------


def _extractor(monkeypatch, answer):
    prompts = []

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": json.dumps(answer)}

    async def fake_post(self, url, *a, **k):
        prompts.append(k["json"]["prompt"])
        return Resp()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return prompts


def test_a_missing_wallet_number_is_extracted_from_the_real_message(monkeypatch):
    """Masked, the model copied "rocket •••••••9099" back as the wallet number."""
    prompts = _extractor(monkeypatch, {"walletNumber": "01609139099"})
    key = ("transfer", "wallet_transfer")
    result = asyncio.run(_REAL_FILL(key, "rocket", {"amount": "200000"}, ["walletNumber"], "(request)",
                                    "send 2 lakh to rocket 01609139099"))
    assert "01609139099" in prompts[0] and "••" not in prompts[0]
    assert result.payload == {"amount": "200000", "walletNumber": "01609139099"}


def test_other_fields_still_see_masked_digit_runs(monkeypatch):
    prompts = _extractor(monkeypatch, {"remarks": "money not received"})
    asyncio.run(_REAL_FILL(("service_requests", "raise_dispute"), None, {}, ["remarks"], "(request)",
                           "money not received, ref 20260929123456"))
    assert "20260929123456" not in prompts[0] and "••" in prompts[0]


# --- a new transfer request is never a "detail change" of the previous one ---------------------


def test_a_request_with_a_destination_type_is_not_filled_as_a_follow_up(monkeypatch):
    """Live: after a bkash transfer, "send 750 to nagad 01730166131" came back as bkash because the
    follow-up filler (which can now read the number) kept the previous subservice."""
    from datetime import datetime, timezone
    from app.banking.session import ChatTurn

    prompts = _extractor(monkeypatch, {"walletNumber": "01730166131", "amount": 750})
    last = ChatTurn(timestamp=datetime.now(timezone.utc), message="send 500 to bkash 01526018159",
                    classification={"type": "BANKING_SERVICE", "category": "transfer", "service": "wallet_transfer",
                                    "subservice": "bkash", "request": {"walletNumber": "01526018159", "amount": 500}})
    result = asyncio.run(_REAL_FILL_PENDING([last], "send 750 to nagad 01730166131"))
    assert result is None          # classified as a new request instead
    assert prompts == []           # and the extractor was not even asked


def test_a_fee_follow_up_is_still_filled_from_the_last_request(monkeypatch):
    from datetime import datetime, timezone
    from app.banking.session import ChatTurn

    _extractor(monkeypatch, {"transactionType": "nagad"})
    chat_module_types = chat_module.fee_transaction_types
    monkeypatch.setattr(chat_module, "fee_transaction_types", lambda *a, **k: ["bkash", "nagad", "rocket"])
    monkeypatch.setattr(chat_module, "_wallet_ids", lambda: ["bkash", "nagad", "rocket"])
    last = ChatTurn(timestamp=datetime.now(timezone.utc), message="bkash fee for 500",
                    classification={"type": "BANKING_SERVICE", "category": "fees", "service": "fee_quote",
                                    "subservice": None, "request": {"transactionType": "bkash", "amount": 500}})
    result = asyncio.run(_REAL_FILL_PENDING([last], "and for nagad?"))
    assert result is not None and result.payload["transactionType"] == "nagad"
    assert chat_module_types is not None
