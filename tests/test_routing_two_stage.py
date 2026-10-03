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
    assert allowed == DOMAINS[domain][1]
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
            return {"response": json.dumps({"domain": "not-a-domain"})}

    async def fake_post(self, *args, **kwargs):
        return FakeResp()

    monkeypatch.setattr(routing.httpx.AsyncClient, "post", fake_post)
    assert asyncio.run(routing._pick_domain("hi", None)) is None
