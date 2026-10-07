"""payload.pending on missing-field clarifications (the app uses it to show a box), the
complaint/dispute asks in particular; and the stickiness fix for the follow-up context."""
import asyncio

import app.banking.routing as routing_module
import app.routes.chat as chat_module
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, Clarification
from app.banking.session import ChatTurn
from datetime import datetime, timezone

from tests.conftest import AUTH_HEADERS
from tests.test_chat_banking_flow import _install_session_fakes, _parse_sse

JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}


def _post(client, monkeypatch, result, message="x"):
    async def fake_classify(message, recent_turns=None):
        return result

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id="cust-pending")

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    _install_session_fakes(monkeypatch)
    resp = client.post("/chat", json={"message": message}, headers=JWT_HEADERS)
    assert resp.status_code == 200
    return next(data for name, data in _parse_sse(resp.text) if name == "result")


def test_pending_payload_shape():
    assert chat_module._pending_payload("support", "submit_complaint", None, ["description"]) == {
        "pending": {"category": "support", "service": "submit_complaint", "subservice": None,
                    "missingFields": ["description"]}}


def test_complaint_without_text_asks_with_pending_so_the_app_can_show_a_box(client, monkeypatch):
    result = _post(client, monkeypatch, BankingService("support", "submit_complaint", None, None), "I want to complain")
    assert result["type"] == "CLARIFICATION_REQUIRED"
    assert result["category"] is None  # unchanged: the clarification itself carries no route
    assert result["payload"] == {"pending": {"category": "support", "service": "submit_complaint",
                                             "subservice": None, "missingFields": ["description"]}}


def test_dispute_without_a_reason_asks_with_pending(client, monkeypatch):
    async def known_bank_data(customer_identity, token, category, service, subservice, payload, context):
        # the bank lookup already found the account and the transaction
        return {**(payload or {}), "accountNumber": "100126000056", "transactionReferenceNo": "T1"}, None

    monkeypatch.setattr(chat_module, "_prefill_from_bank", known_bank_data)
    result = _post(client, monkeypatch, BankingService("service_requests", "raise_dispute", None, None), "dispute")
    assert result["type"] == "CLARIFICATION_REQUIRED"
    pending = result["payload"]["pending"]
    assert (pending["category"], pending["service"]) == ("service_requests", "raise_dispute")
    assert pending["missingFields"] == ["remarks"]  # never the account or reference the bank already knows


def test_a_plain_classifier_clarification_carries_no_pending(client, monkeypatch):
    result = _post(client, monkeypatch, Clarification("what do they need", ("Balance",)), "help")
    assert result["type"] == "CLARIFICATION_REQUIRED"
    assert result["payload"] is None


def test_followup_note_only_applies_when_the_message_asks_for_nothing_of_its_own(monkeypatch):
    """A complaint right after a dispute used to be read as a detail of that dispute."""
    sent = []

    async def fake_post_classification(messages):
        sent.append(messages)
        return None

    monkeypatch.setattr(routing_module, "_post_classification", fake_post_classification)
    last = ChatTurn(timestamp=datetime.now(timezone.utc), message="raise a dispute about my transaction",
                    classification={"type": "BANKING_SERVICE", "category": "service_requests",
                                    "service": "raise_dispute", "subservice": None, "request": {}})
    try:
        asyncio.run(routing_module.classify("I want to make a complaint", [last]))
    except Exception:
        pass
    note = next((m["content"] for batch in sent for m in batch if "PREVIOUS ANSWERED REQUEST" in m.get("content", "")), "")
    assert "ONLY when it asks for nothing of its own" in note
    assert "is a NEW request" in note
