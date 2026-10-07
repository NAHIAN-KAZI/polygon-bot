"""Two-stage classification (domain -> service) and the description-driven prompt."""
import asyncio
import json
from collections import Counter

import pytest

from app.banking import routing
from app.banking.routing import (
    DOMAINS,
    SERVICE_DESCRIPTIONS,
    _domain_scope,
    _render_taxonomy,
    build_system_prompt,
)
from app.banking.session import ChatTurn

# Captured at import, before conftest's autouse fixture replaces it with "no domain".
_REAL_PICK_DOMAIN = routing._pick_domain

_TAXONOMY = {
    "categories": [
        {"id": "account_info", "name": "Account Information", "services": [
            {"id": "balance", "name": "Balance"}, {"id": "cards", "name": "Cards"}]},
        {"id": "fees", "name": "Fees", "services": [{"id": "fee_quote", "name": "Fee Quote"}]},
        {"id": "payments", "name": "Payments", "services": [{"id": "zakat", "name": "Zakat"}]},
    ]
}


def test_every_described_service_belongs_to_exactly_one_domain():
    counts = Counter(key for _, (_, keys) in DOMAINS.items() for key in keys)
    assert all(counts[key] == 1 for key in SERVICE_DESCRIPTIONS)
    assert set(counts) <= set(SERVICE_DESCRIPTIONS)


def test_render_taxonomy_lists_described_services_with_description_and_others_name_only():
    text = _render_taxonomy(_TAXONOMY)
    assert 'category="account_info" service="balance"' in text
    assert SERVICE_DESCRIPTIONS[("account_info", "balance")][0] in text
    assert "zakat (Zakat)" in text


def test_render_taxonomy_filters_to_allowed_domain_and_can_drop_other_services():
    text = _render_taxonomy(_TAXONOMY, frozenset({("fees", "fee_quote")}), include_other=False)
    assert 'service="fee_quote"' in text
    assert 'service="balance"' not in text
    assert "zakat" not in text


def test_system_prompt_has_no_copyable_concrete_example_values():
    prompt = build_system_prompt(_TAXONOMY)
    for literal in ("1234567890", "01812345678", "5000", "Ashan", "Dipu"):
        assert literal not in prompt


@pytest.mark.parametrize("domain", [d for d, (_, keys) in DOMAINS.items() if keys])
def test_domain_scope_narrows_to_that_domains_services(monkeypatch, domain):
    async def fake_pick(message, recent_turns):
        return domain

    monkeypatch.setattr(routing, "_pick_domain", fake_pick)
    allowed, include_other = asyncio.run(_domain_scope("x", None))
    expected = DOMAINS[domain][1]
    if domain in ("transfers", "fees"):
        # fee vs transfer wording is too close to split: both are always offered
        expected = DOMAINS["transfers"][1] | DOMAINS["fees"][1]
    assert allowed == expected
    assert include_other is False


@pytest.mark.parametrize("domain", ["general", "other", None])
def test_domain_scope_keeps_full_prompt_for_general_other_or_failure(monkeypatch, domain):
    async def fake_pick(message, recent_turns):
        return domain

    monkeypatch.setattr(routing, "_pick_domain", fake_pick)
    assert asyncio.run(_domain_scope("x", None)) == (None, True)


def test_domain_scope_always_includes_the_pending_clarifications_service(monkeypatch):
    async def fake_pick(message, recent_turns):
        return "transfers"

    monkeypatch.setattr(routing, "_pick_domain", fake_pick)
    turn = ChatTurn(timestamp=None, message="fees", classification={
        "type": "CLARIFICATION_REQUIRED", "category": "fees", "service": "fee_quote"})
    allowed, _ = asyncio.run(_domain_scope("to bkash", [turn]))
    assert ("fees", "fee_quote") in allowed


def test_pick_domain_returns_none_on_unknown_domain(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": json.dumps({"domain": "not-a-domain"})}}

    async def fake_post(self, *args, **kwargs):
        return FakeResp()

    monkeypatch.setattr(routing.httpx.AsyncClient, "post", fake_post)
    assert asyncio.run(_REAL_PICK_DOMAIN("hi", None)) is None


# --- stage 1 also says what the customer wants: "see" or "do" ------------------------------------


class _Resp:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": self._content}}


def _stage1_says(monkeypatch, payload):
    sent = []

    async def fake_post(self, url, *args, **kwargs):
        sent.append((url, kwargs["json"]))
        return _Resp(payload if isinstance(payload, str) else json.dumps(payload))

    monkeypatch.setattr(routing.httpx.AsyncClient, "post", fake_post)
    return sent


@pytest.mark.parametrize("wants", ["see", "do"])
def test_pick_domain_reads_what_the_customer_wants(monkeypatch, wants):
    sent = _stage1_says(monkeypatch, {"domain": "cards", "wants": wants})
    picked = asyncio.run(_REAL_PICK_DOMAIN("my card", None))
    assert picked == "cards" and picked.wants == wants
    assert isinstance(picked, str)  # a plain str for every existing caller
    url, body = sent[0]
    assert url.endswith("/api/chat")
    assert body["messages"][0]["role"] == "system" and body["messages"][-1] == {"role": "user", "content": "my card"}


@pytest.mark.parametrize("wants", ["maybe", "", None, 5, ["do"], "DO"])
def test_pick_domain_ignores_an_invalid_wants(monkeypatch, wants):
    _stage1_says(monkeypatch, {"domain": "cards", "wants": wants})
    picked = asyncio.run(_REAL_PICK_DOMAIN("my card", None))
    assert picked == "cards" and picked.wants is None


def test_pick_domain_without_wants_still_picks_the_domain(monkeypatch):
    _stage1_says(monkeypatch, {"domain": "accounts"})
    picked = asyncio.run(_REAL_PICK_DOMAIN("balance", None))
    assert picked == "accounts" and picked.wants is None


@pytest.mark.parametrize("payload", ["not json", {"domain": "nope", "wants": "do"}, {"wants": "do"}])
def test_pick_domain_failures_are_none(monkeypatch, payload):
    _stage1_says(monkeypatch, payload)
    assert asyncio.run(_REAL_PICK_DOMAIN("x", None)) is None


def _scope(monkeypatch, domain, wants, turns=None):
    picked = routing._Domain(domain)
    picked.wants = wants

    async def fake_pick(message, recent_turns):
        return picked

    monkeypatch.setattr(routing, "_pick_domain", fake_pick)
    return asyncio.run(_domain_scope("x", turns))


def test_wants_do_keeps_only_the_services_that_do_something(monkeypatch):
    full = DOMAINS["cards"][1]
    allowed, include_other = _scope(monkeypatch, "cards", "do")
    assert allowed == full & routing._DO_KEYS
    assert allowed and allowed < full  # the status lookups are gone
    assert include_other is False
    assert ("card_services", "frezz_unfrezz") in allowed


def test_wants_do_falls_back_to_the_whole_domain_when_it_has_no_do_service(monkeypatch):
    lookups = frozenset({("account_info", "balance"), ("account_info", "accounts")})
    monkeypatch.setattr(routing, "DOMAINS", {**DOMAINS, "lookups": ("only looks", lookups)})
    allowed, _ = _scope(monkeypatch, "lookups", "do")
    assert allowed == lookups


def test_wants_see_removes_the_app_actions_but_keeps_the_lookups(monkeypatch):
    full = DOMAINS["cards"][1]
    assert full & routing.ui_actions.keys()  # the domain does have app actions
    allowed, _ = _scope(monkeypatch, "cards", "see")
    assert allowed == full - routing.ui_actions.keys()
    assert allowed and not (allowed & routing.ui_actions.keys())


@pytest.mark.parametrize("wants", [None, "maybe", "", 7])
def test_unknown_wants_leaves_the_domain_unchanged(monkeypatch, wants):
    allowed, _ = _scope(monkeypatch, "cards", wants)
    assert allowed == DOMAINS["cards"][1]


def test_a_plain_str_domain_has_no_wants_and_is_unchanged(monkeypatch):
    async def fake_pick(message, recent_turns):
        return "cards"

    monkeypatch.setattr(routing, "_pick_domain", fake_pick)
    allowed, _ = asyncio.run(_domain_scope("x", None))
    assert allowed == DOMAINS["cards"][1]


def test_wants_do_still_adds_the_pending_service_and_the_fee_transfer_pair(monkeypatch):
    turn = ChatTurn(timestamp=None, message="fees", classification={
        "type": "CLARIFICATION_REQUIRED", "category": "account_info", "service": "balance"})
    allowed, _ = _scope(monkeypatch, "transfers", "do", [turn])
    assert ("account_info", "balance") in allowed  # the pending question's service
    assert DOMAINS["fees"][1] <= allowed and DOMAINS["transfers"][1] <= allowed


def test_do_services_are_real_described_services_or_app_actions():
    for key in routing._DO_KEYS:
        assert key in SERVICE_DESCRIPTIONS, key
