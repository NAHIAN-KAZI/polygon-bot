"""T-77 follow-ups: undo requests are not freezes, fields the customer already gave are not
asked again, raw ids never reach the composer, and every classifier Clarification is
composed with the services it could have meant.

Real in-memory session store; every bank/model call is mocked at its import site
(httpx.AsyncClient.post for the JSON-extraction helpers). Nothing reaches a network.
"""
import asyncio
import json

import httpx
import pytest

import app.banking.routing as routing_module
import app.banking.session as session_module
import app.routes.chat as chat_module
from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, Clarification, UnknownService
from app.banking.session import ChatTurn
from app.conversation.persona import GLOBAL_PERSONA, KIND_PURPOSE

from tests.conftest import AUTH_HEADERS

# Captured at import, before conftest's autouse fixture swaps in stand-ins.
_REAL_UNDO = chat_module._undo_request
_REAL_GROUND = chat_module._ground_freeze_request
_REAL_FILL_KNOWN = chat_module._fill_known_from_message

PHONE = "01712345678"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}
FREEZE = BankingService("card_services", "frezz_unfrezz", None, {"cardId": "41", "cardLast4": "0251"})
DISPUTE = ("service_requests", "raise_dispute")
SAVINGS = {"id": 11, "accountNumber": "2001000011112222", "accountType": "SAVINGS", "balance": 0}
TXNS = [
    {"transactionId": "TXN-RAW-A", "txnTime": "2026-10-01T09:00:00", "type": "DEBIT", "amount": 500,
     "transactionType": "ATM", "accountNumber": SAVINGS["accountNumber"]},
    {"transactionId": "TXN-RAW-B", "txnTime": "2026-10-02T10:30:00", "type": "DEBIT", "amount": 2000,
     "transactionType": "NPSB", "accountNumber": SAVINGS["accountNumber"]},
]


# --- model mocks ------------------------------------------------------------------


class _Resp:
    def __init__(self, obj):
        self._obj = obj

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": json.dumps(self._obj)}


def _model_json(monkeypatch, obj=None, error=None):
    """Patch the JSON-extraction model call; returns the prompts it was sent."""
    prompts = []

    async def fake_post(self, url, *args, **kwargs):
        prompts.append(kwargs.get("json", {}).get("prompt", ""))
        if error is not None:
            raise error
        return _Resp(obj)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return prompts


def _run(coro):
    return asyncio.run(coro)


# --- 1. undo requests are never a freeze --------------------------------------------


@pytest.mark.parametrize("message", [
    "please unfreeze my card", "unblock my card", "free my card", "reactivate my card",
    "can you release the block on my card",
])
def test_undo_request_returns_the_customers_own_words(monkeypatch, message):
    _model_json(monkeypatch, {"undo_request": message})
    assert _run(_REAL_UNDO([message])) == message


@pytest.mark.parametrize("obj", [
    {"undo_request": None}, {"undo_request": "null"}, {"undo_request": ""}, {}, ["unfreeze"], "unfreeze",
])
def test_no_undo_request_when_the_model_finds_none(monkeypatch, obj):
    _model_json(monkeypatch, obj)
    assert _run(_REAL_UNDO(["freeze my card"])) is None


def test_an_undo_quote_the_customer_never_wrote_is_ignored(monkeypatch):
    _model_json(monkeypatch, {"undo_request": "please unfreeze and reactivate my frozen card"})
    assert _run(_REAL_UNDO(["freeze my card, it was stolen"])) is None


@pytest.mark.parametrize("error", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")])
def test_undo_check_failure_is_none(monkeypatch, error):
    _model_json(monkeypatch, error=error)
    assert _run(_REAL_UNDO(["unfreeze my card"])) is None


def test_undo_prompt_masks_long_digit_runs(monkeypatch):
    prompts = _model_json(monkeypatch, {"undo_request": None})
    _run(_REAL_UNDO(["unfreeze card 4001230000000251"]))
    assert "4001230000000251" not in prompts[0] and "••••••••••••0251" in prompts[0]


def test_ground_freeze_turns_an_undo_request_into_the_unfreeze_app_action(monkeypatch):
    async def undo(messages):
        return "unfreeze my card"

    async def facts(messages):
        raise AssertionError("an undo request never reaches the freeze grounding")

    monkeypatch.setattr(chat_module, "_undo_request", undo)
    monkeypatch.setattr(chat_module, "_freeze_request_facts", facts)
    out = _run(_REAL_GROUND(FREEZE, "unfreeze my card", []))
    assert out == BankingService("app_actions", "card_unfreeze", None, None)


def test_ground_freeze_keeps_a_plain_freeze_request(monkeypatch):
    async def undo(messages):
        return None

    async def facts(messages):
        return "it was stolen", "freeze my card"

    monkeypatch.setattr(chat_module, "_undo_request", undo)
    monkeypatch.setattr(chat_module, "_freeze_request_facts", facts)
    out = _run(_REAL_GROUND(FREEZE, "freeze my card, it was stolen", []))
    assert isinstance(out, BankingService) and out.payload["reason"] == "it was stolen"


def test_undo_is_only_checked_for_the_freeze_service(monkeypatch):
    async def undo(messages):
        raise AssertionError("not a freeze")

    monkeypatch.setattr(chat_module, "_undo_request", undo)
    other = BankingService("account_info", "balance", None, None)
    assert _run(_REAL_GROUND(other, "unfreeze", [])) is other


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(session_module, "_sessions", {})
    state = {"sends": [], "fulfills": [], "classified": [], "composed": [], "route": None,
             "accounts": [SAVINGS], "pick": 0}

    async def verify_jwt(token):
        return CustomerIdentity(customer_id=PHONE)

    async def classify(message, recent_turns=None):
        state["classified"].append(message)
        return state["route"] or Clarification(question="What would you like to do?")

    async def send_otp(phone):
        state["sends"].append(phone)

    async def fulfill(customer_identity, jwt, category, service, subservice, payload):
        state["fulfills"].append((category, service, dict(payload) if payload else payload))
        if (category, service) == ("account_info", "accounts"):
            return AdapterResult(data={"data": {"accounts": state["accounts"]}})
        if (category, service) == ("polygon_services", "transaction_history"):
            return AdapterResult(data={"transactions": TXNS})
        return AdapterResult(data={"success": True})

    async def pick(message, candidates):
        return state["pick"]

    async def compose(kind, facts, *, message="", history=None, must_include=None):
        state["composed"].append({"kind": kind, "facts": facts, "must": must_include or {}})
        return f"{kind}: " + "; ".join(f"{k}: {v}" for k, v in {**facts, **(must_include or {})}.items())

    async def compose_stream(kind, facts, *, message="", history=None, must_include=None):
        yield await compose(kind, facts, message=message, history=history, must_include=must_include)

    monkeypatch.setattr(chat_module, "verify_jwt", verify_jwt)
    monkeypatch.setattr(chat_module, "classify", classify)
    monkeypatch.setattr(chat_module, "send_otp", send_otp)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fulfill)
    monkeypatch.setattr(chat_module, "_llm_pick_candidate", pick)
    monkeypatch.setattr(chat_module, "compose", compose)
    monkeypatch.setattr(chat_module, "compose_stream", compose_stream)
    return state


def _post(client, message, payload=None):
    body = {"message": message}
    if payload is not None:
        body["payload"] = payload
    resp = client.post("/chat", json=body, headers=JWT_HEADERS)
    assert resp.status_code == 200
    events = []
    for block in resp.text.strip("\n").split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((name, data))
    return events


def _result(events):
    return next(d for n, d in events if n == "result")


def _token(events):
    return "".join(d["token"] for n, d in events if n == "token")


@pytest.mark.parametrize("message", ["unfreeze my card", "unblock it please", "free my card", "reactivate my card"])
def test_an_undo_request_opens_the_unfreeze_screen_and_sends_no_code_or_confirmation(client, env, monkeypatch, message):
    env["route"] = FREEZE
    monkeypatch.setattr(chat_module, "_ground_freeze_request", _REAL_GROUND)
    _model_json(monkeypatch, {"undo_request": message})  # the undo extraction; freeze facts below
    monkeypatch.setattr(chat_module, "_undo_request", _REAL_UNDO)

    async def facts(messages):
        raise AssertionError("never reached for an undo request")

    monkeypatch.setattr(chat_module, "_freeze_request_facts", facts)
    events = _post(client, message)
    result = _result(events)
    assert result["type"] == "APP_ACTION"
    assert (result["category"], result["service"]) == ("app_actions", "card_unfreeze")
    assert result["payload"]["ui"]["screen"] == "FreezeCardScreen"
    assert env["composed"][-1]["kind"] == "redirect"
    assert env["sends"] == [] and env["fulfills"] == []
    assert session_module.get_session(PHONE)[-1].classification["type"] == "APP_ACTION"


def test_a_plain_freeze_request_is_unaffected_by_the_undo_check(client, env, monkeypatch):
    env["route"] = FREEZE
    monkeypatch.setattr(chat_module, "_ground_freeze_request", _REAL_GROUND)

    async def undo(messages):
        return None

    async def facts(messages):
        return "it was stolen", "freeze my card"

    monkeypatch.setattr(chat_module, "_undo_request", undo)
    monkeypatch.setattr(chat_module, "_freeze_request_facts", facts)
    events = _post(client, "freeze my card, it was stolen")
    assert _result(events)["type"] == "CONFIRMATION_REQUIRED"
    assert env["composed"][-1]["kind"] == "confirm"
    assert env["sends"] == []


# --- 2. fields the customer already gave are not asked again ----------------------------

_DISPUTE_MESSAGE = "my ATM withdrawal failed and the ATM did not give cash"


def _dispute_route(payload=None):
    return BankingService("service_requests", "raise_dispute", None, payload)


def test_fill_known_finds_a_missing_free_text_field_in_the_same_message(monkeypatch):
    prompts = _model_json(monkeypatch, {"remarks": "the ATM did not give cash"})
    out = _run(_REAL_FILL_KNOWN(_dispute_route(), _DISPUTE_MESSAGE))
    assert out.payload == {"remarks": "the ATM did not give cash"}
    assert (out.category, out.service) == DISPUTE
    # only the field that is missing AND the customer's to give is asked of the model
    assert '"remarks"' in prompts[0]
    assert "accountNumber" not in prompts[0] and "transactionReferenceNo" not in prompts[0]


def test_fill_known_drops_a_value_not_in_the_customers_own_words(monkeypatch):
    _model_json(monkeypatch, {"remarks": "my debit card was cloned by a stranger"})
    result = _dispute_route()
    out = _run(_REAL_FILL_KNOWN(result, "please raise a dispute"))
    assert out is result  # nothing grounded -> unchanged -> the customer is asked


def test_fill_known_never_asks_for_what_the_bank_looks_up(monkeypatch):
    prompts = _model_json(monkeypatch, {"accountNumber": "2001000011112222", "transactionReferenceNo": "TXN-1"})
    result = _dispute_route({"remarks": "ATM did not give cash"})
    # nothing the customer owes is missing -> no model call at all, result unchanged
    assert _run(_REAL_FILL_KNOWN(result, _DISPUTE_MESSAGE)) is result
    assert prompts == []


def test_fill_known_keeps_existing_values_and_adds_to_them(monkeypatch):
    _model_json(monkeypatch, {"amount": 5000})
    result = BankingService("transfer", "bank_transfer", "other_bank", {"accountNumber": "1234567890"})
    out = _run(_REAL_FILL_KNOWN(result, "send 5000 to 1234567890"))
    assert out.payload == {"accountNumber": "1234567890", "amount": 5000}
    assert out.subservice == "other_bank"


def test_fill_known_never_touches_changes_that_are_gathered_step_by_step(monkeypatch):
    prompts = _model_json(monkeypatch, {"nickName": "Rafi"})
    result = BankingService("profile_update", "update_nickname", None, None)
    assert _run(_REAL_FILL_KNOWN(result, "change my nickname to Rafi")) is result
    assert prompts == []


def test_fill_known_validates_amounts_against_the_message(monkeypatch):
    _model_json(monkeypatch, {"amount": 3000})
    fee = BankingService("fees", "fee_quote", None, {"transactionType": "bkash"})
    assert _run(_REAL_FILL_KNOWN(fee, "fee to send 5000 via bkash")) is fee
    _model_json(monkeypatch, {"amount": 50000})
    out = _run(_REAL_FILL_KNOWN(fee, "fee to send 50k via bkash"))
    assert out.payload == {"transactionType": "bkash", "amount": 50000}


@pytest.mark.parametrize("result", [
    Clarification(question="?"),
    UnknownService("x", "y", None),
    BankingService("account_info", "balance", None, None),                              # nothing required
    BankingService("card_services", "frezz_unfrezz", None, {"cardId": "41"}),           # never followed up
])
def test_fill_known_leaves_other_results_alone_without_a_model_call(monkeypatch, result):
    prompts = _model_json(monkeypatch, {"reason": "lost"})
    assert _run(_REAL_FILL_KNOWN(result, "freeze my card, i lost it")) is result
    assert prompts == []


def test_fill_known_model_failure_leaves_the_result_unchanged(monkeypatch):
    _model_json(monkeypatch, error=httpx.ConnectError("down"))
    result = _dispute_route()
    assert _run(_REAL_FILL_KNOWN(result, _DISPUTE_MESSAGE)) is result


def test_dispute_with_remarks_in_the_message_is_not_asked_again(client, env, monkeypatch):
    env["route"] = _dispute_route()
    monkeypatch.setattr(chat_module, "_fill_known_from_message", _REAL_FILL_KNOWN)
    _model_json(monkeypatch, {"remarks": "the ATM did not give cash"})
    events = _post(client, _DISPUTE_MESSAGE)
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE" and result["routing"]["action"] == "raise_dispute"
    assert result["payload"]["remarks"] == "the ATM did not give cash"
    assert result["payload"]["executed"] is False
    summary = env["composed"][-1]
    assert summary["kind"] == "summary" and summary["facts"]["their reason"] == "the ATM did not give cash"
    assert all(c["kind"] != "ask" for c in env["composed"])
    # looked up from the customer's own data, never asked
    assert [(c, s) for c, s, _ in env["fulfills"]] == [
        ("account_info", "accounts"), ("polygon_services", "transaction_history")]


def test_dispute_with_an_ungrounded_value_asks_for_the_reason_only(client, env, monkeypatch):
    env["route"] = _dispute_route()
    monkeypatch.setattr(chat_module, "_fill_known_from_message", _REAL_FILL_KNOWN)
    _model_json(monkeypatch, {"remarks": "my card was cloned"})
    events = _post(client, "i want to raise a dispute")
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"
    asked = env["composed"][-1]
    assert asked["kind"] == "ask"
    assert asked["facts"]["missing"] == [chat_module._CLARIFICATION_FIELD_DESCRIPTIONS["remarks"]]
    # the bank looks the account and transaction up: neither is ever asked of the customer
    assert "reference" not in json.dumps(asked["facts"]["missing"]).lower()
    assert "account" not in json.dumps(asked["facts"]["missing"]).lower()


# --- 3. raw transaction reference ids never reach the composer ---------------------------


def test_known_field_phrases_show_the_transaction_summary_not_the_reference():
    phrases = chat_module._known_field_phrases(
        {"transactionReferenceNo": "TXN-RAW-A", "transactionSummary": "Tk 5.00 ATM debit on 2026-10-01"})
    assert phrases == ["transaction: Tk 5.00 ATM debit on 2026-10-01"]
    assert chat_module._known_field_phrases({"transactionReferenceNo": "TXN-RAW-A"}) == []


def test_dispute_summary_without_a_summary_has_no_transaction_fact():
    _, facts, must = chat_module._dispute_summary_say({"accountNumber": "100126000056",
                                                       "transactionReferenceNo": "TXN-RAW-A"})
    assert "transaction" not in facts
    assert "TXN-RAW-A" not in repr((facts, must))


def test_no_raw_reference_id_in_any_composer_call_across_the_dispute_flow(client, env, monkeypatch):
    env["route"] = _dispute_route({"remarks": "ATM did not give cash"})
    env["pick"] = None  # no clear match -> the customer is shown the list
    events = _post(client, "dispute the ATM thing")
    assert _result(events)["type"] == "TRANSACTION_SELECTION_REQUIRED"
    chosen = _post(client, "the first one", {"transactionId": "TXN-RAW-A"})
    assert _result(chosen)["type"] == "BANKING_SERVICE"
    assert _result(chosen)["payload"]["transactionReferenceNo"] == "TXN-RAW-A"  # data for the app is fine
    spoken = json.dumps(env["composed"])
    assert "TXN-RAW" not in spoken
    assert "2001000011112222" not in spoken
    assert env["composed"][-1]["kind"] == "summary" and "transaction" in env["composed"][-1]["facts"]


# --- 4. every classifier Clarification is composed, with the options ------------------------


def test_a_clarification_is_composed_with_the_services_it_could_have_meant(client, env):
    env["route"] = Clarification("Which one do you mean?", options=("Balance", "Fee quote", "Cards"))
    events = _post(client, "help with money")
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"
    composed = env["composed"][-1]
    assert composed["kind"] == "clarify"
    assert composed["facts"]["what is unclear"] == "Which one do you mean?"
    assert composed["facts"]["could mean"] == ["Balance", "Fee quote", "Cards"]
    assert "can help with" not in composed["facts"]
    assert _token(events).startswith("clarify:")
    assert session_module.get_session(PHONE)[-1].classification["question"] == _token(events)


def test_a_clarification_without_options_offers_what_the_bot_can_help_with(client, env):
    env["route"] = Clarification("What do you need?")
    _post(client, "hmm")
    facts = env["composed"][-1]["facts"]
    assert "could mean" not in facts
    assert facts["can help with"] and len(facts["can help with"]) >= 3


def test_the_generic_fallback_question_is_not_used_as_a_hint(client, env):
    env["route"] = Clarification(chat_module._CLARIFICATION_FALLBACK)
    _post(client, "hmm")
    assert env["composed"][-1]["facts"]["what is unclear"] == "what the customer would like to do"


# --- 5. classify() attaches the options -------------------------------------------------------

TAXONOMY = {"categories": [
    {"id": "account_info", "services": [{"id": "balance", "name": "Balance"}, {"id": "cards", "name": "Cards"}]},
    {"id": "fees", "services": [{"id": "fee_quote", "name": "Fee quote"}]},
    {"id": "support", "services": [{"id": f"s{i}", "name": f"Service {i}"} for i in range(10)]},
]}


def test_option_names_come_from_the_live_taxonomy_for_the_allowed_services(monkeypatch):
    monkeypatch.setattr(routing_module, "get_taxonomy", lambda: TAXONOMY)
    allowed = frozenset({("account_info", "balance"), ("fees", "fee_quote"), ("nope", "x")})
    assert routing_module._option_names(allowed) == ("Balance", "Fee quote")
    assert routing_module._option_names(None) == () and routing_module._option_names(frozenset()) == ()


def test_option_names_are_capped(monkeypatch):
    monkeypatch.setattr(routing_module, "get_taxonomy", lambda: TAXONOMY)
    allowed = frozenset(("support", f"s{i}") for i in range(10))
    assert len(routing_module._option_names(allowed)) == 8
    assert len(routing_module._option_names(allowed, limit=3)) == 3


def _stub_classify(monkeypatch, result, allowed):
    async def scope(message, recent_turns):
        return allowed, False

    async def scoped(message, recent_turns, allowed_, include_other):
        assert allowed_ == allowed
        return result

    monkeypatch.setattr(routing_module, "_domain_scope", scope)
    monkeypatch.setattr(routing_module, "_classify_scoped", scoped)
    monkeypatch.setattr(routing_module, "get_taxonomy", lambda: TAXONOMY)


def test_classify_attaches_the_scoped_service_names_to_a_clarification(monkeypatch):
    _stub_classify(monkeypatch, Clarification("Which?"), frozenset({("account_info", "balance"), ("account_info", "cards")}))
    out = _run(routing_module.classify("money stuff"))
    assert out == Clarification("Which?", ("Balance", "Cards"))


def test_classify_keeps_options_the_classifier_already_set(monkeypatch):
    _stub_classify(monkeypatch, Clarification("Which?", ("Mine",)), frozenset({("fees", "fee_quote")}))
    assert _run(routing_module.classify("x")).options == ("Mine",)


@pytest.mark.parametrize("result", [
    BankingService("account_info", "balance", None, None), UnknownService("a", "b", None),
])
def test_classify_passes_other_results_through(monkeypatch, result):
    _stub_classify(monkeypatch, result, frozenset({("fees", "fee_quote")}))
    assert _run(routing_module.classify("x")) is result


def test_clarification_options_default_to_empty():
    assert Clarification("q").options == ()


# --- 6. history and persona wording -------------------------------------------------------------


def test_history_is_marked_as_context_only_and_precedes_the_latest_message():
    from app.conversation.composer import build_messages
    user = build_messages("answer", {"x": "y"}, "latest question", [("Customer", "earlier")], {})[1]["content"]
    header = "Earlier in this chat (context only; answer the customer's latest message below, not these):"
    assert header in user
    assert user.index(header) < user.index("Customer: earlier") < user.index("Customer: latest question")


def test_persona_answers_the_latest_message_and_clarify_names_the_options():
    assert "3. Answer the customer's latest message; use earlier messages only when the latest one " \
           "depends on them." in GLOBAL_PERSONA
    assert "option" in KIND_PURPOSE["clarify"].lower()
