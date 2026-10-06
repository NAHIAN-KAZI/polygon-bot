"""T-79: requests the chat hands to the app (app/banking/ui_actions.py).

Registry integrity against the app's own docs, the grounding of prefilled fields, the
APP_ACTION outcome, and the /chat wiring: no bank call, no OTP, no confirmation. The two
planning docs are read from the repo (planning/input/); when the tests run inside the
backend container, mount them: -v "$PWD/planning:/app/planning:ro".
Nothing here reaches a network.
"""
import json
import re
from pathlib import Path

import pytest

import app.banking.session as session_module
import app.banking.taxonomy as taxonomy_module
import app.routes.chat as chat_module
from app.banking import routing, ui_actions
from app.banking.adapters.base import AdapterResult
from app.banking.identity import CustomerIdentity
from app.banking.routing import BankingService, Clarification

from tests.conftest import AUTH_HEADERS

PLANNING = Path(__file__).resolve().parent.parent / "planning" / "input"
PHONE = "01712345678"
JWT_HEADERS = {**AUTH_HEADERS, "Authorization": "Bearer sometoken"}
ALL = sorted(ui_actions.UI_ACTIONS)


def _doc(name: str) -> str:
    path = PLANNING / name
    assert path.exists(), f"{path} not found (mount planning/ into the container)"
    return path.read_text(encoding="utf-8")


# --- registry integrity ------------------------------------------------------------------


def test_there_are_29_actions_with_unique_ids_matching_their_keys():
    actions = list(ui_actions.UI_ACTIONS.values())
    assert len(actions) == 29
    assert len({a.id for a in actions}) == len(actions)
    assert all(key == a.id for key, a in ui_actions.UI_ACTIONS.items())
    assert ui_actions.CATEGORY == "app_actions"


@pytest.mark.parametrize("action_id", ALL)
def test_every_action_is_well_formed(action_id):
    a = ui_actions.get(action_id)
    assert a.domain in routing.DOMAINS
    assert a.kind in {"screen", "info", "unavailable"}
    assert a.name and a.description and a.needs and a.rows
    assert a.route is None or a.route.startswith("/")
    # a screen action opens something
    if a.kind == "screen":
        assert a.screen
    if a.kind == "unavailable":
        assert a.screen is None and a.route is None
    # prompts and facts are never quoted sentences
    for text in (a.description, a.needs, a.name):
        assert '"' not in text, f"{action_id}: double quote in {text!r}"
    fields = [field for field, _ in a.prefill]
    assert len(fields) == len(set(fields))
    assert all(meaning and '"' not in meaning for _, meaning in a.prefill)


def test_every_screen_is_a_real_app_screen():
    screen_map = _doc("API_SCREEN_MAP.md")
    for a in ui_actions.UI_ACTIONS.values():
        if a.screen:
            assert a.screen in screen_map, f"{a.id}: screen {a.screen} is not in API_SCREEN_MAP.md"


def test_every_row_is_in_the_implementation_status_doc():
    status = _doc("INTENT_IMPLEMENTATION_STATUS.md")
    rows = set(re.findall(r"^\| (\d+\.\d+) ", status, re.MULTILINE))
    for a in ui_actions.UI_ACTIONS.values():
        for row in a.rows:
            assert row in rows, f"{a.id}: row {row} is not in INTENT_IMPLEMENTATION_STATUS.md"


def test_routes_look_like_the_apps_route_table():
    routes = [a.route for a in ui_actions.UI_ACTIONS.values() if a.route]
    assert routes and all(re.fullmatch(r"/[a-z0-9_/:]+", r) for r in routes)


def test_helpers_agree_with_the_registry():
    assert ui_actions.get("nope") is None
    assert ui_actions.keys() == frozenset((ui_actions.CATEGORY, i) for i in ALL)
    by_domain = set()
    for domain in routing.DOMAINS:
        by_domain |= ui_actions.keys_for_domain(domain)
    assert by_domain == ui_actions.keys()
    assert ui_actions.keys_for_domain("no_such_domain") == frozenset()


def test_catalog_category_lists_every_action_as_an_active_service():
    category = ui_actions.catalog_category()
    assert category["id"] == "app_actions" and category["isActive"] is True
    assert [s["id"] for s in category["services"]] == [a.id for a in ui_actions._LIST]
    assert all(s["isActive"] and s["name"] for s in category["services"])


@pytest.mark.parametrize("action_id", ALL)
def test_every_action_is_routable(action_id):
    a = ui_actions.get(action_id)
    key = (ui_actions.CATEGORY, action_id)
    description, prefill_fields = routing.SERVICE_DESCRIPTIONS[key]
    assert description == a.description
    assert prefill_fields == tuple(field for field, _ in a.prefill)
    assert key in routing.DOMAINS[a.domain][1]


def test_every_action_is_a_valid_taxonomy_path(monkeypatch):
    categories = taxonomy_module._SYNTHETIC_CATEGORIES
    assert any(c["id"] == "app_actions" for c in categories)
    monkeypatch.setattr(taxonomy_module, "_cache", {"categories": categories})
    monkeypatch.setattr(taxonomy_module, "_index", taxonomy_module._build_index(categories))
    for action_id in ALL:
        assert taxonomy_module.is_valid_path("app_actions", action_id), action_id
        assert not taxonomy_module.is_valid_path("app_actions", action_id, "sub")
    assert not taxonomy_module.is_valid_path("app_actions", "no_such_action")


# --- _ui_prefill ---------------------------------------------------------------------------


def _prefill(action_id, payload, message):
    return chat_module._ui_prefill(ui_actions.get(action_id), payload, message)


def test_a_written_amount_with_a_unit_word_is_kept():
    assert _prefill("card_limit_change", {"requestedLimit": 50000}, "raise my limit to 50k") == {"requestedLimit": 50000}
    assert _prefill("transfer_limit_change", {"newLimit": 150000}, "make my transfer limit 1.5 lakh") == {"newLimit": 150000}


def test_an_amount_the_customer_never_wrote_is_dropped():
    assert _prefill("card_limit_change", {"requestedLimit": 70000}, "raise my limit to 50k") == {}
    assert _prefill("cash_by_code", {"amount": 5000}, "send cash by code") == {}


def test_card_last4_only_if_the_digits_appear_in_the_message():
    assert _prefill("card_pin_reset", {"cardLast4": "0251"}, "reset the pin of my card 0251") == {"cardLast4": "0251"}
    assert _prefill("card_pin_reset", {"cardLast4": "9999"}, "reset the pin of my card 0251") == {}
    assert _prefill("card_pin_reset", {"cardLast4": "0251"}, "reset my card pin") == {}


def test_a_full_card_number_is_reduced_to_its_last_four():
    out = _prefill("card_close", {"cardLast4": "4001230000000251"}, "close card ending 0251")
    assert out == {"cardLast4": "0251"}


def test_recipient_mobile_must_be_written_by_the_customer():
    message = "send cash by code to 01812345678, 2000 taka"
    out = _prefill("cash_by_code", {"recipientMobile": "01812345678", "amount": 2000}, message)
    assert out == {"recipientMobile": "01812345678", "amount": 2000}
    assert _prefill("cash_by_code", {"recipientMobile": "01999999999"}, message) == {}


def test_free_text_is_kept_only_when_in_the_customers_own_words():
    message = "i want to change my email because i moved house"
    out = _prefill("profile_change_request",
                   {"reason": "i moved house", "fieldName": "email", "requestedValue": "a@b.com"}, message)
    assert out == {"reason": "i moved house", "fieldName": "email"}  # the new email was never written
    assert _prefill("profile_change_request", {"reason": "my identity was stolen"}, message) == {}
    assert _prefill("beneficiary_edit", {"nickname": "Mom"}, "rename my beneficiary Rahim to Mom") == {"nickname": "Mom"}


def test_undeclared_and_empty_values_are_dropped():
    message = "reset the pin of my card 0251"
    payload = {"cardLast4": "0251", "pin": "1234", "amount": 500, "anything": "x"}
    assert _prefill("card_pin_reset", payload, message) == {"cardLast4": "0251"}
    assert _prefill("card_pin_reset", {"cardLast4": ""}, message) == {}
    assert _prefill("card_pin_reset", {"cardLast4": None}, message) == {}
    assert _prefill("card_pin_reset", None, message) == {}
    assert _prefill("card_limit_cancel", {"cardLast4": "0251"}, message) == {}  # declares no prefill


@pytest.mark.parametrize("action_id", ALL)
def test_prefill_never_returns_a_field_the_action_does_not_declare(action_id):
    a = ui_actions.get(action_id)
    junk = {"cardLast4": "0251", "amount": 500, "reason": "x", "nickname": "x", "pin": "1", "otp": "2"}
    declared = {field for field, _ in a.prefill}
    assert set(chat_module._ui_prefill(a, junk, "0251 500 x")) <= declared


# --- _ui_action_outcome ----------------------------------------------------------------------


def _outcome(action_id, payload=None, message=""):
    return chat_module._ui_action_outcome(ui_actions.get(action_id), payload, message)


def test_a_screen_action_hands_the_app_the_screen_and_what_the_customer_said():
    outcome = _outcome("card_pin_reset", {"cardLast4": "0251"}, "reset the pin of my card 0251")
    a = ui_actions.get("card_pin_reset")
    assert outcome.result_type == "APP_ACTION"
    assert (outcome.category, outcome.service, outcome.subservice) == ("app_actions", "card_pin_reset", None)
    assert outcome.result_payload == {
        "ui": {"kind": "screen", "title": a.name, "screen": "SelectCardForPinResetScreen",
               "route": "/set_reset_card_pin", "prefill": {"cardLast4": "0251"}, "needs": a.needs},
        "executed": False,
    }
    assert outcome.routing == {"category": "app_actions", "service": "card_pin_reset",
                               "subservice": None, "action": "card_pin_reset"}
    kind, facts, must = outcome.say
    assert kind == "redirect"
    assert facts["what they will do there"] == a.needs
    assert facts["already filled in"] == {"cardLast4": "0251"}
    assert facts["done in chat"].startswith("no")


def test_nothing_grounded_means_no_prefill_and_no_already_filled_in_fact():
    outcome = _outcome("card_pin_reset", {"cardLast4": "9999"}, "reset my card pin")
    assert outcome.result_payload["ui"]["prefill"] is None
    kind, facts, _ = outcome.say
    assert kind == "redirect" and "already filled in" not in facts


def test_an_info_action_is_not_in_chat():
    outcome = _outcome("card_details_reveal", None, "show me my card cvv")
    kind, facts, _ = outcome.say
    assert kind == "not_in_chat"
    assert outcome.result_type == "APP_ACTION"
    assert outcome.result_payload["ui"]["kind"] == "info"
    assert outcome.result_payload["executed"] is False
    assert "sensitive" in facts["what to know"]


def test_an_unavailable_action_is_not_done_and_changes_nothing():
    outcome = _outcome("qr_payment_cards", None, "which cards are on qr")
    kind, facts, _ = outcome.say
    assert kind == "not_done" and facts["changed"] == "nothing"
    assert outcome.result_payload["ui"]["screen"] is None and outcome.result_payload["ui"]["route"] is None


@pytest.mark.parametrize("action_id", ALL)
def test_every_action_yields_a_well_formed_outcome(action_id):
    a = ui_actions.get(action_id)
    outcome = _outcome(action_id, None, "")
    ui = outcome.result_payload["ui"]
    assert outcome.result_type == "APP_ACTION" and outcome.result_payload["executed"] is False
    assert (ui["kind"], ui["screen"], ui["route"], ui["needs"]) == (a.kind, a.screen, a.route, a.needs)
    assert outcome.routing["action"] == action_id
    assert outcome.say[0] == {"screen": "redirect", "info": "not_in_chat", "unavailable": "not_done"}[a.kind]
    assert json.dumps(outcome.result_payload)  # serialisable for the SSE event


# --- end to end through /chat ------------------------------------------------------------------


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(session_module, "_sessions", {})
    state = {"sends": [], "fulfills": [], "classified": [], "composed": [], "route": None}

    async def verify_jwt(token):
        return CustomerIdentity(customer_id=PHONE)

    async def classify(message, recent_turns=None):
        state["classified"].append(message)
        route = state["route"]
        return route.pop(0) if isinstance(route, list) else (route or Clarification(question="What?"))

    async def send_otp(phone):
        state["sends"].append(phone)

    async def fulfill(*args, **kwargs):
        state["fulfills"].append(args[2:5])
        return AdapterResult(data={"balance": "500.00"})

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


def test_app_action_end_to_end_opens_the_screen_without_any_bank_step(client, env):
    env["route"] = BankingService("app_actions", "card_limit_change", None,
                                  {"cardLast4": "0251", "requestedLimit": 50000})
    events = _post(client, "raise the limit of my credit card 0251 to 50k")
    result = _result(events)
    assert result["type"] == "APP_ACTION"
    assert (result["category"], result["service"], result["subservice"]) == ("app_actions", "card_limit_change", None)
    assert result["payload"]["ui"]["screen"] == "CardLimitChangeScreen"
    assert result["payload"]["ui"]["route"] == "/card_limit_change_request"
    assert result["payload"]["ui"]["prefill"] == {"cardLast4": "0251", "requestedLimit": 50000}
    assert result["payload"]["executed"] is False
    assert result["routing"] == {"category": "app_actions", "service": "card_limit_change",
                                 "subservice": None, "action": "card_limit_change"}
    assert env["fulfills"] == [] and env["sends"] == []
    assert len(env["composed"]) == 1 and env["composed"][0]["kind"] == "redirect"
    assert _token(events).startswith("redirect:")
    assert "CONFIRMATION_REQUIRED" not in json.dumps(events)


def test_a_prefill_value_the_customer_never_wrote_is_dropped_end_to_end(client, env):
    env["route"] = BankingService("app_actions", "card_limit_change", None,
                                  {"cardLast4": "9999", "requestedLimit": 70000})
    events = _post(client, "i want a higher limit on my credit card")
    assert _result(events)["payload"]["ui"]["prefill"] is None
    assert "already filled in" not in env["composed"][0]["facts"]
    assert "9999" not in json.dumps(env["composed"]) and "70000" not in json.dumps(env["composed"])


@pytest.mark.parametrize("action_id,expected", [("card_details_reveal", "not_in_chat"),
                                                ("qr_payment_cards", "not_done")])
def test_info_and_unavailable_actions_end_to_end(client, env, action_id, expected):
    env["route"] = BankingService("app_actions", action_id, None, None)
    events = _post(client, "show me that")
    assert _result(events)["type"] == "APP_ACTION"
    assert env["composed"][0]["kind"] == expected
    assert env["fulfills"] == [] and env["sends"] == []


def test_the_turn_is_recorded_as_app_action_and_the_next_message_is_fresh(client, env):
    env["route"] = [BankingService("app_actions", "card_pin_reset", None, None),
                    BankingService("account_info", "balance", None, None)]
    _post(client, "reset my card pin")
    stored = session_module.get_session(PHONE)[-1].classification
    assert stored["type"] == "APP_ACTION"
    assert (stored["category"], stored["service"]) == ("app_actions", "card_pin_reset")
    assert "question" not in stored and "missingFields" not in stored

    events = _post(client, "what is my balance")
    assert env["classified"] == ["reset my card pin", "what is my balance"]  # no pending state swallowed it
    assert _result(events)["type"] == "BANKING_SERVICE"


def test_an_unknown_app_action_id_is_not_dispatched_as_an_app_action(client, env):
    env["route"] = BankingService("app_actions", "no_such_action", None, None)
    events = _post(client, "do something")
    assert _result(events)["type"] != "APP_ACTION"
    assert env["sends"] == []


# --- unfreeze safety net ----------------------------------------------------------------------

FREEZE = BankingService("card_services", "frezz_unfrezz", None, {"cardId": "41", "cardLast4": "0251"})


@pytest.mark.parametrize("message", ["please unfreeze my card", "unblock my card", "free my card",
                                     "reactivate my card"])
def test_an_unfreeze_request_is_handed_to_the_unfreeze_screen(client, env, monkeypatch, message):
    env["route"] = FREEZE  # the classifier sends it to the freeze service
    monkeypatch.setattr(chat_module, "_ground_freeze_request", _REAL_GROUND)

    async def undo(messages):
        return message

    async def facts(messages):
        raise AssertionError("an unfreeze request never reaches the freeze grounding")

    monkeypatch.setattr(chat_module, "_undo_request", undo)
    monkeypatch.setattr(chat_module, "_freeze_request_facts", facts)
    events = _post(client, message)
    result = _result(events)
    assert result["type"] == "APP_ACTION"
    assert (result["category"], result["service"]) == ("app_actions", "card_unfreeze")
    assert result["payload"]["ui"]["screen"] == "FreezeCardScreen"
    assert result["payload"]["ui"]["route"] == "/freeze_card"
    assert env["sends"] == [] and env["fulfills"] == []
    assert "CONFIRMATION_REQUIRED" not in json.dumps(events) and "OTP_REQUIRED" not in json.dumps(events)
    assert env["composed"][0]["kind"] == "redirect"


def test_ground_freeze_request_maps_an_undo_request_to_card_unfreeze(monkeypatch):
    import asyncio

    async def undo(messages):
        return "unfreeze my card"

    monkeypatch.setattr(chat_module, "_undo_request", undo)
    out = asyncio.run(_REAL_GROUND(FREEZE, "unfreeze my card", []))
    assert out == BankingService("app_actions", "card_unfreeze", None, None)


# Captured at import, before conftest's autouse fixture swaps in a stand-in.
_REAL_GROUND = chat_module._ground_freeze_request
