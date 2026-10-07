"""Doing something to the customer's card, account or profile needs words for WHAT to do
and to WHAT. A bare "Card", "Cancel" or "Pay" used to start a card freeze or closing.
`_ground_requested_action` keeps the classification only when both quotes are in the
customer's message; otherwise the bot asks what they want, offering what it can do for that
kind of request. The model call (/api/generate, JSON) is mocked; nothing reaches a network.
"""
import asyncio
import json

import httpx
import pytest

import app.banking.routing as routing_module
import app.banking.session as session_module
import app.routes.chat as chat_module
from app.banking import ui_actions
from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity
from app.banking.routing import DOMAINS, BankingService, Clarification, UnknownService

from tests.conftest import AUTH_HEADERS

# Captured at import, before conftest's autouse fixture swaps in a pass-through.
_REAL = chat_module._ground_requested_action

PHONE = "01712345678"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}
FREEZE = ("card_services", "frezz_unfrezz")

TAXONOMY = {"categories": [
    {"id": "card_services", "services": [{"id": "frezz_unfrezz", "name": "Freeze Card"}]},
    {"id": "card_requests", "services": [{"id": "report_lost_card", "name": "Report Lost Card"}]},
    {"id": "account_info", "services": [{"id": "cards", "name": "Cards"}, {"id": "balance", "name": "Balance"}]},
    ui_actions.catalog_category(),
]}


class _Resp:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._text}


def _model(monkeypatch, action=None, obj=None, raw=None, error=None):
    prompts = []

    async def fake_post(self, url, *args, **kwargs):
        prompts.append(kwargs["json"]["prompt"])
        assert url.endswith("/api/generate")
        assert kwargs["json"]["format"] == "json" and kwargs["json"]["options"]["temperature"] == 0
        if error is not None:
            raise error
        return _Resp(raw if raw is not None else json.dumps({"action": action, "object": obj}))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return prompts


@pytest.fixture
def taxonomy(monkeypatch):
    monkeypatch.setattr(routing_module, "get_taxonomy", lambda: TAXONOMY)
    return TAXONOMY


def _ground(result, message):
    return asyncio.run(_REAL(result, message))


def _freeze(payload=None):
    return BankingService(*FREEZE, None, payload)


# --- unit -------------------------------------------------------------------------------------


def test_both_quotes_in_the_message_keep_the_result(monkeypatch):
    prompts = _model(monkeypatch, "freeze", "my card")
    result = _freeze()
    assert _ground(result, "please freeze my card") is result
    assert len(prompts) == 1


@pytest.mark.parametrize("action,obj", [
    ("freeze", None),                       # an action word with nothing it is for
    (None, "card"),                         # only a thing named
    (None, None),
    ("", ""),
    ("null", "none"),
    ("freeze", "my savings account"),       # the object isn't in the message
    ("close it forever", "card"),           # the action isn't in the message
    ("cancel", "my card"),                  # neither is
])
def test_a_missing_or_ungrounded_part_asks_what_they_want(monkeypatch, taxonomy, action, obj):
    _model(monkeypatch, action, obj)
    out = _ground(_freeze(), "Card")
    assert isinstance(out, Clarification)
    assert "what they want to do" in out.question


def test_the_clarification_offers_what_can_be_done_for_that_kind_of_request(monkeypatch, taxonomy):
    _model(monkeypatch, None, None)
    out = _ground(_freeze(), "Card")
    expected = routing_module._option_names(DOMAINS["cards"][1] & chat_module._ACT_KEYS)
    assert out.options == expected and out.options
    # card actions (from the app-action catalog and the card services), not lookups
    assert "Unfreeze card" in out.options and "Freeze Card" in out.options
    assert "Cards" not in out.options and "Balance" not in out.options


def test_a_key_with_no_domain_gets_no_options(monkeypatch, taxonomy):
    _model(monkeypatch, None, None)
    monkeypatch.setattr(chat_module, "_ACT_KEYS", chat_module._ACT_KEYS | {("x", "y")})
    out = _ground(BankingService("x", "y", None, None), "do it")
    assert isinstance(out, Clarification) and out.options == ()


@pytest.mark.parametrize("payload", [{"cardId": "41"}, {"reason": "it was stolen"}, {"nickName": "Rafi"}])
def test_specifics_already_in_the_payload_skip_the_model(monkeypatch, payload):
    prompts = _model(monkeypatch, None, None)
    result = BankingService("profile_update", "update_nickname", None, payload) if "nickName" in payload \
        else _freeze(payload)
    assert _ground(result, "Card") is result
    assert prompts == []


def test_a_model_exception_keeps_the_classifiers_choice(monkeypatch):
    _model(monkeypatch, error=httpx.ConnectError("down"))
    result = _freeze()
    assert _ground(result, "Card") is result
    _model(monkeypatch, error=httpx.ReadTimeout("slow"))
    assert _ground(result, "Card") is result


@pytest.mark.parametrize("raw", ["not json at all", "[]", '"freeze"', "null", "5"])
def test_unparseable_or_non_dict_output_is_nothing_written(monkeypatch, taxonomy, raw):
    _model(monkeypatch, raw=raw)
    if raw == "not json at all":
        # a JSON syntax error is a failed check (like an exception): the choice stands
        result = _freeze()
        assert _ground(result, "Card") is result
    else:
        assert isinstance(_ground(_freeze(), "Card"), Clarification)


@pytest.mark.parametrize("result", [
    BankingService("transfer", "bank_transfer", "other_bank", None),
    BankingService("transfer", "wallet_transfer", "bkash", None),
    BankingService("polygon_services", "beneficiary", None, None),
    BankingService("support", "submit_complaint", None, None),
    BankingService("service_requests", "raise_dispute", None, None),
    BankingService("account_info", "balance", None, None),
    BankingService("account_info", "cards", None, None),
    BankingService("fees", "fee_quote", None, None),
    Clarification(question="?"),
    UnknownService("a", "b", None),
])
def test_transfers_complaints_disputes_lookups_and_other_results_pass_through(monkeypatch, result):
    prompts = _model(monkeypatch, None, None)
    assert _ground(result, "Card") is result
    assert prompts == []


def test_the_act_keys_exclude_the_flows_with_their_own_gathering():
    keys = chat_module._ACT_KEYS
    for excluded in [("transfer", "bank_transfer"), ("transfer", "wallet_transfer"),
                     ("polygon_services", "beneficiary"), ("support", "submit_complaint"),
                     ("service_requests", "raise_dispute")]:
        assert excluded not in keys
    assert FREEZE in keys and ("card_requests", "report_lost_card") in keys
    assert ("profile_update", "update_nickname") in keys and ui_actions.keys() <= keys
    assert keys == routing_module._DO_KEYS - {
        ("transfer", "bank_transfer"), ("transfer", "wallet_transfer"), ("polygon_services", "beneficiary"),
        ("support", "submit_complaint"), ("service_requests", "raise_dispute")}


def test_app_actions_need_both_words_too(monkeypatch, taxonomy):
    _model(monkeypatch, None, "card")
    out = _ground(BankingService("app_actions", "card_close", None, None), "Card")
    assert isinstance(out, Clarification)


def test_domain_of_finds_the_services_domain():
    assert chat_module._domain_of(FREEZE) == "cards"
    assert chat_module._domain_of(("app_actions", "card_close")) == "cards"
    assert chat_module._domain_of(("nope", "nope")) is None


def test_prompt_masks_long_digit_runs(monkeypatch):
    prompts = _model(monkeypatch, "close", "card")
    _ground(_freeze(), "close card 4001230000000251")
    assert "4001230000000251" not in prompts[0] and "••••••••••••0251" in prompts[0]


def test_render_taxonomy_lists_the_app_actions_before_other_categories():
    text = routing_module._render_taxonomy(TAXONOMY)
    lines = [ln for ln in text.splitlines() if ln.startswith("- category=")]
    positions = [i for i, ln in enumerate(lines) if 'category="app_actions"' in ln]
    others = [i for i, ln in enumerate(lines) if 'category="app_actions"' not in ln]
    assert positions and others
    assert max(positions) < min(others)
    # stable: the other categories keep the taxonomy's own order
    ordered = [ln.split('"')[1] for ln in lines if 'category="app_actions"' not in ln]
    seen = list(dict.fromkeys(ordered))
    assert seen == [c for c in ("card_services", "card_requests", "account_info") if c in seen]


# --- end to end through /chat -------------------------------------------------------------------


@pytest.fixture
def env(monkeypatch, taxonomy):
    monkeypatch.setattr(session_module, "_sessions", {})
    state = {"fulfills": [], "composed": [], "route": None, "sends": []}

    async def verify_jwt(token):
        return CustomerIdentity(customer_id=PHONE)

    async def classify(message, recent_turns=None):
        return state["route"]

    async def send_otp(phone):
        state["sends"].append(phone)

    async def fulfill(customer_identity, jwt, category, service, subservice, payload):
        state["fulfills"].append((category, service))
        return AdapterResult(data={"cards": [{"id": "41", "cardNumber": "4001230000000251"}]})

    async def compose(kind, facts, *, message="", history=None, must_include=None):
        state["composed"].append({"kind": kind, "facts": facts, "must": must_include or {}})
        return f"{kind}: " + "; ".join(f"{k}: {v}" for k, v in {**facts, **(must_include or {})}.items())

    async def compose_stream(kind, facts, *, message="", history=None, must_include=None):
        yield await compose(kind, facts, message=message, history=history, must_include=must_include)

    monkeypatch.setattr(chat_module, "verify_jwt", verify_jwt)
    monkeypatch.setattr(chat_module, "classify", classify)
    monkeypatch.setattr(chat_module, "send_otp", send_otp)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fulfill)
    monkeypatch.setattr(chat_module, "compose", compose)
    monkeypatch.setattr(chat_module, "compose_stream", compose_stream)
    monkeypatch.setattr(chat_module, "_ground_requested_action", _REAL)
    return state


def _post(client, message):
    resp = client.post("/chat", json={"message": message}, headers=JWT_HEADERS)
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


def test_a_bare_card_asks_what_they_want_instead_of_starting_a_freeze(client, env, monkeypatch):
    _model(monkeypatch, None, "Card")
    env["route"] = _freeze()
    events = _post(client, "Card")
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"
    composed = env["composed"]
    assert [c["kind"] for c in composed] == ["clarify"]
    assert composed[0]["facts"]["could mean"]
    assert "Freeze Card" in composed[0]["facts"]["could mean"] and "Unfreeze card" in composed[0]["facts"]["could mean"]
    assert env["fulfills"] == [] and env["sends"] == []  # no card lookup, no code
    assert "CONFIRMATION_REQUIRED" not in json.dumps(events) and "OTP_REQUIRED" not in json.dumps(events)
    stored = session_module.get_session(PHONE)[-1].classification
    assert stored["type"] == "CLARIFICATION_REQUIRED"


def test_a_grounded_freeze_request_still_proceeds(client, env, monkeypatch):
    prompts = _model(monkeypatch, "freeze", "my card")
    env["route"] = _freeze()
    events = _post(client, "freeze my card, it was stolen")
    assert len(prompts) == 1
    assert env["fulfills"] == [("account_info", "cards")]  # the freeze flow's own card lookup ran
    kinds = [c["kind"] for c in env["composed"]]
    assert "clarify" not in kinds  # not asked what they want
    assert _result(events)["type"] in {"CLARIFICATION_REQUIRED", "CONFIRMATION_REQUIRED"}
    assert env["sends"] == []  # a code is never sent before the yes/no


def test_a_freeze_with_the_card_and_reason_already_known_does_not_call_the_model(client, env, monkeypatch):
    prompts = _model(monkeypatch, None, None)
    env["route"] = _freeze({"cardId": "41", "cardLast4": "0251", "reason": "stolen"})
    events = _post(client, "my card was stolen")
    assert prompts == []
    assert _result(events)["type"] == "CONFIRMATION_REQUIRED"
