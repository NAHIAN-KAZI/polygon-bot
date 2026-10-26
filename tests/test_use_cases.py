"""The use-case catalog the back office switches on and off (T-108)."""
from collections import Counter

from app.banking import routing, taxonomy, ui_actions, use_cases


def test_every_described_service_belongs_to_exactly_one_use_case():
    described = {key for key in routing.SERVICE_DESCRIPTIONS if key[0] != ui_actions.CATEGORY}
    covered = Counter(key for u in use_cases.EXPLICIT for key in u.keys)
    assert described <= set(covered), f"services with no use case: {sorted(described - set(covered))}"
    assert [key for key, n in covered.items() if n > 1] == []


def test_every_app_action_has_its_own_use_case():
    ids = {u.id for u in use_cases.EXPLICIT}
    for action_id in ui_actions.UI_ACTIONS:
        assert f"{ui_actions.CATEGORY}.{action_id}" in ids


def test_ids_are_unique_and_intents_are_known():
    ids = [u.id for u in use_cases.EXPLICIT]
    assert len(ids) == len(set(ids))
    known = {intent for intent, _ in use_cases.INTENTS}
    assert {u.intent for u in use_cases.EXPLICIT} <= known


def test_use_case_for_resolves_a_routed_service():
    assert use_cases.use_case_for("card_services", "frezz_unfrezz") == "card_services.frezz_unfrezz"
    assert use_cases.use_case_for("account_info", "account_transactions") == "polygon_services.transaction_history"
    assert use_cases.use_case_for("app_actions", "card_close") == "app_actions.card_close"
    assert use_cases.use_case_for("payments", "mobile_recharge") == "app_actions.mobile_recharge"
    assert use_cases.use_case_for("no_such", "service") is None
    assert use_cases.use_case_for(None, None) is None


def test_freeze_offers_the_app_screen_when_switched_off_and_a_plain_service_does_not():
    action = use_cases.ui_action_for_use_case("card_services.frezz_unfrezz")
    assert action is not None and action.route == "/freeze_card"
    assert use_cases.ui_action_for_use_case("account_info.balance") is None
    assert use_cases.ui_action_for_use_case("nope") is None


def test_unavailable_app_actions_are_not_switchable():
    by_id = {u.id: u for u in use_cases.EXPLICIT}
    assert by_id["app_actions.other_banks_list"].switchable is False
    assert by_id["card_services.frezz_unfrezz"].switchable is True


def test_platform_services_the_bot_never_routes_are_listed_as_not_in_chat(monkeypatch):
    monkeypatch.setattr(taxonomy, "get_taxonomy", lambda: {"categories": [
        {"id": "utility", "services": [{"id": "electricity", "name": "Electricity bill"}]},
        {"id": "account_info", "services": [{"id": "balance", "name": "Balance"}]},
        {"id": ui_actions.CATEGORY, "services": [{"id": "card_close", "name": "Close card"}]},
    ]})
    extra = [u for u in use_cases.all_use_cases() if u.intent == use_cases.NOT_IN_CHAT]
    assert [(u.id, u.name, u.switchable) for u in extra] == [("utility.electricity", "Electricity bill", False)]


def test_catalog_shape():
    catalog = use_cases.catalog()
    intents = {i["id"]: i for i in catalog["intents"]}
    freeze = next(u for u in intents["CARD_MANAGEMENT"]["useCases"] if u["id"] == "card_services.frezz_unfrezz")
    assert freeze == {"id": "card_services.frezz_unfrezz", "name": "Freeze a card", "kind": "confirmed_change",
                      "appScreen": True, "switchable": True, "keys": [["card_services", "frezz_unfrezz"]], "rows": []}
    assert all(i["useCases"] for i in catalog["intents"])


def test_route_returns_the_catalog_and_needs_the_api_key(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "API_KEY", "secret-key")
    ok = client.get("/chat/use-cases", headers={"X-API-Key": "secret-key"})
    assert ok.status_code == 200 and ok.json()["intents"]
    assert client.get("/chat/use-cases").status_code == 401
    assert client.get("/chat/use-cases", headers={"X-API-Key": "wrong"}).status_code == 401
