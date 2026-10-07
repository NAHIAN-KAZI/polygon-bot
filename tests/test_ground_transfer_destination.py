"""A transfer's destination type must come from words the customer wrote.

Live: a bare "send money" was routed to a guessed own-account transfer and answered as
"you only have one account". `_ground_transfer_destination` keeps the classifier's
subservice only when the customer's own words (or a destination number they gave) say where
the money goes; otherwise the subservice is dropped and the bot asks. The model call
(/api/generate, JSON) is mocked; nothing reaches a network.
"""
import asyncio
import json

import httpx
import pytest

import app.banking.session as session_module
import app.routes.chat as chat_module
from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, Clarification, UnknownService
from app.routes import chat as chat_routes

from tests.conftest import AUTH_HEADERS

# Captured at import, before conftest's autouse fixture swaps in a pass-through.
_REAL = chat_module._ground_transfer_destination

PHONE = "01712345678"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}


class _Resp:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": self._text}


def _model(monkeypatch, destination=..., raw=None, error=None):
    """Mock the extraction call; returns the prompts it was sent."""
    prompts = []

    async def fake_post(self, url, *args, **kwargs):
        prompts.append(kwargs["json"]["prompt"])
        assert url.endswith("/api/generate")
        assert kwargs["json"]["format"] == "json" and kwargs["json"]["options"]["temperature"] == 0
        if error is not None:
            raise error
        return _Resp(raw if raw is not None else json.dumps({"destination": destination}))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return prompts


def _ground(result, message):
    return asyncio.run(_REAL(result, message))


def _wallet(payload=None, sub="rocket"):
    return BankingService("transfer", "wallet_transfer", sub, payload)


def _bank(payload=None, sub="own_account"):
    return BankingService("transfer", "bank_transfer", sub, payload)


# --- unit ------------------------------------------------------------------------------------


def test_a_grounded_destination_keeps_the_transfer_as_classified(monkeypatch):
    _model(monkeypatch, "my rocket")
    result = _wallet({"amount": 500})
    assert _ground(result, "send 500 to my rocket") is result


@pytest.mark.parametrize("destination", [None, "", "   ", "null", "none", "to my wife's account in Dubai bank"])
def test_no_or_ungrounded_destination_drops_the_subservice_and_keeps_the_payload(monkeypatch, destination):
    _model(monkeypatch, destination)
    out = _ground(_wallet({"amount": 500}), "send 500 taka")
    assert out == BankingService("transfer", "wallet_transfer", None, {"amount": 500})
    assert (out.category, out.service, out.subservice) == ("transfer", "wallet_transfer", None)


def test_a_bank_transfer_with_a_guessed_type_is_dropped_the_same_way(monkeypatch):
    _model(monkeypatch, None)
    out = _ground(_bank(), "send money")
    assert out == BankingService("transfer", "bank_transfer", None, None)


def test_a_destination_number_the_customer_wrote_counts_and_needs_no_model_call(monkeypatch):
    prompts = _model(monkeypatch, None)
    result = _wallet({"walletNumber": "01812345678", "amount": 500})
    assert _ground(result, "send 500 to 01812345678") is result
    bank = _bank({"accountNumber": "2001000011112222"}, "other_bank")
    assert _ground(bank, "transfer to 2001 0000 1111 2222") is bank
    assert prompts == []


def test_a_destination_number_not_in_the_message_does_not_count(monkeypatch):
    prompts = _model(monkeypatch, None)
    out = _ground(_wallet({"walletNumber": "01812345678"}), "send some money")
    assert out.subservice is None and out.payload == {"walletNumber": "01812345678"}
    assert len(prompts) == 1


def test_a_short_number_is_not_a_destination(monkeypatch):
    prompts = _model(monkeypatch, None)
    out = _ground(_bank({"accountNumber": "1234"}), "send to 1234")
    assert out.subservice is None
    assert len(prompts) == 1


@pytest.mark.parametrize("raw", ["[]", '"my rocket"', "{}", "null", '{"destination": 5}'])
def test_well_formed_but_unusable_output_never_grounds_a_destination(monkeypatch, raw):
    _model(monkeypatch, raw=raw)
    assert _ground(_wallet(), "send money").subservice is None


def test_unparseable_output_is_a_failed_check_and_keeps_the_classifiers_choice(monkeypatch):
    _model(monkeypatch, raw="not json at all")
    result = _wallet()
    assert _ground(result, "send money") is result


@pytest.mark.parametrize("error", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")])
def test_model_failure_keeps_the_classifiers_choice(monkeypatch, error):
    _model(monkeypatch, error=error)
    result = _wallet({"amount": 500})
    assert _ground(result, "send 500") is result


@pytest.mark.parametrize("result", [
    Clarification(question="?"),
    UnknownService("x", "y", None),
    BankingService("fees", "fee_quote", None, {"amount": 500}),
    BankingService("account_info", "balance", "balance", None),
    BankingService("transfer", "bank_transfer", None, {"amount": 500}),  # no subservice yet: nothing to check
    BankingService("transfer", "wallet_transfer", "", None),
    BankingService("beneficiary_management", "beneficiary_add", None, None),
])
def test_other_results_pass_through_without_a_model_call(monkeypatch, result):
    prompts = _model(monkeypatch, None)
    assert _ground(result, "send money") is result
    assert prompts == []


def test_long_digit_runs_are_masked_in_the_prompt(monkeypatch):
    prompts = _model(monkeypatch, None)
    _ground(_bank({"accountNumber": "999"}), "send 500 from 2001000011112222 please")
    assert "2001000011112222" not in prompts[0]
    assert "••••••••••••2222" in prompts[0]


def test_the_transfer_keys_are_the_two_transfer_services():
    assert set(chat_module._TRANSFER_KEYS) == {("transfer", "bank_transfer"), ("transfer", "wallet_transfer")}


# --- end to end through /chat ---------------------------------------------------------------------


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(session_module, "_sessions", {})
    state = {"fulfills": [], "composed": [], "route": None, "classified": []}

    async def verify_jwt(token):
        return CustomerIdentity(customer_id=PHONE)

    async def classify(message, recent_turns=None):
        state["classified"].append(message)
        return state["route"]

    async def fulfill(customer_identity, jwt, category, service, subservice, payload):
        state["fulfills"].append((category, service, subservice))
        return AdapterResult(data={"data": {"accounts": [{"id": 1, "accountNumber": "2001000011112222",
                                                          "accountType": "SAVINGS"}]}})

    async def compose(kind, facts, *, message="", history=None, must_include=None):
        state["composed"].append({"kind": kind, "facts": facts, "must": must_include or {}})
        return f"{kind}: " + "; ".join(f"{k}: {v}" for k, v in {**facts, **(must_include or {})}.items())

    async def compose_stream(kind, facts, *, message="", history=None, must_include=None):
        yield await compose(kind, facts, message=message, history=history, must_include=must_include)

    monkeypatch.setattr(chat_module, "verify_jwt", verify_jwt)
    monkeypatch.setattr(chat_module, "classify", classify)
    monkeypatch.setattr(chat_module, "fulfill_banking_service", fulfill)
    monkeypatch.setattr(chat_module, "compose", compose)
    monkeypatch.setattr(chat_module, "compose_stream", compose_stream)
    monkeypatch.setattr(chat_module, "_ground_transfer_destination", _REAL)
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


def test_a_bare_send_money_asks_where_to_send_it_and_never_looks_up_own_accounts(client, env, monkeypatch):
    _model(monkeypatch, None)
    env["route"] = BankingService("transfer", "bank_transfer", "own_account", None)
    events = _post(client, "send money")
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"
    assert env["fulfills"] == []  # no own-account lookup
    kinds = [c["kind"] for c in env["composed"]]
    assert kinds == ["ask"]  # not "only one account" (not_done) and no account selection
    asked = env["composed"][0]["facts"]
    # the types to choose from are in what the composer is given; no transfer type was guessed
    assert asked["request"] == chat_routes.SERVICE_DESCRIPTIONS[("transfer", "bank_transfer")][0]
    assert "transfer type" not in asked
    stored = session_module.get_session(PHONE)[-1].classification
    assert stored["type"] == "CLARIFICATION_REQUIRED" and stored["subservice"] is None
    assert (stored["category"], stored["service"]) == ("transfer", "bank_transfer")


def test_a_grounded_destination_proceeds_as_before(client, env, monkeypatch):
    _model(monkeypatch, "my other account")
    env["route"] = BankingService("transfer", "bank_transfer", "own_account", {"amount": 500})
    events = _post(client, "move 500 to my other account")
    # the own-account flow runs: the customer's accounts are looked up for them
    assert env["fulfills"] == [("account_info", "accounts", None)]
    assert _result(events)["type"] != "CLARIFICATION_REQUIRED"
    assert env["composed"][0]["kind"] in {"not_done", "choose"}


def test_a_grounded_wallet_transfer_reaches_the_summary(client, env, monkeypatch):
    _model(monkeypatch, "to my rocket")
    env["route"] = BankingService("transfer", "wallet_transfer", "rocket",
                                  {"walletNumber": "01812345678", "amount": 500})
    events = _post(client, "send 500 to my rocket 01812345678")
    result = _result(events)
    assert result["type"] == "BANKING_SERVICE" and result["payload"]["executed"] is False
    assert result["routing"]["action"] == "rocket_transfer"
    assert env["composed"][0]["kind"] == "summary"
    assert env["fulfills"] == []


def test_a_wallet_transfer_without_a_written_destination_asks_instead_of_summarising(client, env, monkeypatch):
    _model(monkeypatch, None)
    env["route"] = BankingService("transfer", "wallet_transfer", "rocket", {"amount": 500})
    events = _post(client, "send 500 taka")
    assert _result(events)["type"] == "CLARIFICATION_REQUIRED"
    assert env["composed"][0]["kind"] == "ask"
    assert env["fulfills"] == []
