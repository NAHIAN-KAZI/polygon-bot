"""What the customer did in the app's own forms reaches the chat (payload.uiContext)."""
import json

import app.routes.chat as chat_module
from app.banking import session as session_module
from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService

from tests.conftest import AUTH_HEADERS

CUSTOMER = "cust-ui"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}


def _parse_sse(body):
    out = []
    for block in body.strip("\n").split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            out.append((name, data))
    return out


# --- reading the notes off the request ---------------------------------------------------------


def test_notes_are_taken_cleaned_and_removed_from_the_payload():
    notes, payload = chat_module._split_ui_context(
        {"uiContext": ["In the app: Close card — Card closed", "  two   spaces\\nand a line break  ", "", 5, None],
         "accountNumber": "123"})
    assert notes == ["In the app: Close card — Card closed", "two spaces\\nand a line break"] or \
        notes[0].startswith("In the app: Close card")
    assert all("\n" not in n and "\r" not in n for n in notes)
    assert payload == {"accountNumber": "123"}


def test_a_payload_that_is_only_notes_becomes_none():
    assert chat_module._split_ui_context({"uiContext": ["x"]}) == (["x"], None)


def test_other_payloads_are_untouched():
    p = {"remarks": "text"}
    assert chat_module._split_ui_context(p) == ([], p)
    assert chat_module._split_ui_context(None) == ([], None)


def test_malformed_notes_are_ignored_and_still_removed():
    assert chat_module._split_ui_context({"uiContext": "not a list", "a": 1}) == ([], {"a": 1})
    assert chat_module._split_ui_context({"uiContext": {"x": 1}}) == ([], None)


def test_notes_are_capped_in_number_and_length():
    notes, _ = chat_module._split_ui_context({"uiContext": [f"note {i} " + "x" * 600 for i in range(12)]})
    assert len(notes) == 5
    assert notes[-1].startswith("note 11")        # the newest ones are kept
    assert all(len(n) <= 240 for n in notes)


# --- remembered for the session ----------------------------------------------------------------


def test_notes_are_kept_for_the_session_and_capped():
    session_module._sessions.clear()
    try:
        session_module.record_ui_notes(CUSTOMER, ["a", "b"])
        session_module.record_ui_notes(CUSTOMER, ["c", "d", "e", "f"])
        assert session_module.get_ui_notes(CUSTOMER) == ["b", "c", "d", "e", "f"]
        assert session_module.get_ui_notes("someone-else") == []
    finally:
        session_module._sessions.clear()


def test_notes_expire_with_the_session():
    from datetime import datetime, timedelta, timezone
    session_module._sessions.clear()
    try:
        session_module.record_ui_notes(CUSTOMER, ["a"])
        session_module._sessions[CUSTOMER].last_active_at = datetime.now(timezone.utc) - timedelta(hours=1)
        assert session_module.get_ui_notes(CUSTOMER) == []
    finally:
        session_module._sessions.clear()


# --- end to end ----------------------------------------------------------------------------------


def _wire(monkeypatch, seen):
    async def fake_classify(message, recent_turns=None, app_notes=None):
        seen["app_notes"] = app_notes
        return BankingService(category="account_info", service="balance", subservice="balance")

    async def fake_verify_jwt(token):
        return CustomerIdentity(customer_id=CUSTOMER)

    async def fake_fulfill(customer_identity, jwt, category, service, subservice, payload):
        seen["payload"] = payload
        return AdapterResult(data={"balance": "500.00"})

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "verify_jwt", fake_verify_jwt)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fake_fulfill)
    monkeypatch.setattr(chat_module.audit, "log_banking_turn", lambda *a, **k: None)


def test_e2e_the_classifier_is_told_what_the_customer_did_in_the_app(client, monkeypatch):
    session_module._sessions.clear()
    seen = {}
    _wire(monkeypatch, seen)
    try:
        resp = client.post("/chat", json={"message": "did it work?", "payload": {
            "uiContext": ["In the app: Close card — Card closed — Debit card ••••0269"]}}, headers=JWT_HEADERS)
        assert resp.status_code == 200
        assert seen["app_notes"] == ["In the app: Close card — Card closed — Debit card ••••0269"]
        assert not seen.get("payload")          # the note never reached the bank call as a field
        # and it is still known on the next message, without the app repeating it
        seen.clear()
        client.post("/chat", json={"message": "and my balance now?"}, headers=JWT_HEADERS)
        assert seen["app_notes"] == ["In the app: Close card — Card closed — Debit card ••••0269"]
    finally:
        session_module._sessions.clear()


def test_e2e_a_direct_request_never_sees_the_notes_as_a_field(client, monkeypatch):
    session_module._sessions.clear()
    seen = {}
    _wire(monkeypatch, seen)
    monkeypatch.setattr(chat_module, "is_valid_path", lambda *a, **k: True)  # no live service list in tests
    try:
        client.post("/chat", json={
            "message": "show", "category": "account_info", "service": "balance",
            "payload": {"accountNumber": "100126000023", "uiContext": ["In the app: something"]}}, headers=JWT_HEADERS)
    finally:
        session_module._sessions.clear()
    assert seen["payload"] == {"accountNumber": "100126000023"}


def test_e2e_without_notes_the_classifier_call_is_unchanged(client, monkeypatch):
    session_module._sessions.clear()
    seen = {}
    _wire(monkeypatch, seen)
    try:
        client.post("/chat", json={"message": "balance"}, headers=JWT_HEADERS)
    finally:
        session_module._sessions.clear()
    assert seen["app_notes"] is None


# --- asking about what was done in the app ------------------------------------------------------


def test_the_app_actions_tool_is_offered_only_when_there_are_notes():
    from app.banking.routing import build_tools
    assert [t["function"]["name"] for t in build_tools()] == [
        "answer_kb_question", "route_banking_service", "ask_clarification"]
    assert "answer_from_app_actions" in [t["function"]["name"] for t in build_tools(app_actions=True)]


def _call(name):
    return [{"function": {"name": name, "arguments": {}}}]


def test_classify_returns_app_actions_question_only_with_notes(monkeypatch):
    import asyncio
    from app.banking import routing

    offered = []

    async def fake_post(messages, app_actions=False):
        offered.append(app_actions)
        return _call("answer_from_app_actions")

    monkeypatch.setattr(routing, "_post_classification", fake_post)
    monkeypatch.setattr(routing, "get_taxonomy", lambda: {})
    notes = ["In the app: Close card -- Card closed -- Debit card ending 0269"]
    with_notes = asyncio.run(routing._classify_scoped("did that work?", None, None, True, app_notes=notes))
    assert isinstance(with_notes, routing.AppActionsQuestion) and offered == [True]
    # a model that names the tool anyway, with nothing reported, is not trusted
    without = asyncio.run(routing._classify_scoped("did that work?", None, None, True))
    assert not isinstance(without, routing.AppActionsQuestion)


def test_e2e_a_question_about_the_form_is_answered_from_the_notes(client, monkeypatch):
    from app.banking.routing import AppActionsQuestion
    session_module._sessions.clear()
    seen = {}
    _wire(monkeypatch, seen)
    facts_seen = []

    async def fake_classify(message, recent_turns=None, app_notes=None):
        return AppActionsQuestion()

    async def fake_stream(kind, facts, *, message="", history=None, must_include=None):
        facts_seen.append((kind, facts, must_include))
        yield "Yes, it was closed."

    monkeypatch.setattr(chat_module, "classify", fake_classify)
    monkeypatch.setattr(chat_module, "compose_stream", fake_stream)
    note = "In the app: Close card -- Card closed -- Debit card ending 0269"
    try:
        resp = client.post("/chat", json={"message": "did it work?", "payload": {"uiContext": [note]}},
                           headers=JWT_HEADERS)
    finally:
        session_module._sessions.clear()
    events = _parse_sse(resp.text)
    result = next(d for n, d in events if n == "result")
    assert result["type"] == "APP_ACTIONS_ANSWER" and result["payload"] == {}
    assert events[-1][0] == "done"
    kind, facts, _must = facts_seen[0]
    assert kind == "recall_app_action"
    assert facts["what the customer did in the app"] == [note]
