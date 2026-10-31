"""The cards the bank offers right now, from its own card-products API (T-145).

The knowledge base describes cards in pages and passages, and a question like "which credit cards do you have" only
ever sees the few passages that match, so the answer named some cards and then fell back to networks (Visa,
Mastercard). The live list is complete and exact, so it goes into the answer next to the passages: the list says
*which* cards exist, the passages say what each one gives, costs and requires. A new card in the bank's system shows
up here without a code change.

The list is the bank's catalogue, not the customer's data, so it is kept for a few minutes and shared: a visitor who
is not signed in gets the last list a signed-in customer fetched (the endpoint itself needs a login).
"""
import dataclasses
import logging
import re
import time

from app.banking.adapters.base import AdapterUnavailableError
from app.banking.adapters.real import CardProductsAdapter
from app.config import settings
from app.knowledge.product_cards import ProductCard

logger = logging.getLogger(__name__)

_cache: tuple[float, list[dict]] | None = None


def _rows(data) -> list[dict]:
    """The card rows of an API body, whatever wrapper the bank put around them."""
    if isinstance(data, dict):
        for key in ("data", "cardProducts"):
            if isinstance(data.get(key), list):
                return [r for r in data[key] if isinstance(r, dict)]
        return []
    return [r for r in data or [] if isinstance(r, dict)]


def _card(row: dict) -> dict | None:
    name = str(row.get("tierName") or "").strip()
    if not name or row.get("active") is False:
        return None
    networks = [*(row.get("internationalNetworks") or []), *(row.get("domesticNetworks") or [])]
    return {
        "name": name,
        "type": str(row.get("cardCategory") or "").strip().lower(),
        "network": str(row.get("scheme") or "").strip().title(),
        "networks": [str(n).title() for n in networks],
        "description": str(row.get("description") or "").strip(),
        # what the app needs to draw the card's artwork (it paints it from the catalogue's own fields)
        "scheme_code": str(row.get("scheme") or "").strip().upper(),
        "routing_profile": str(row.get("routingProfile") or "").strip().upper() or None,
        "capabilities": [str(c).strip().upper() for c in row.get("capabilities") or [] if str(c).strip()][:12],
    }


def parse(body) -> list[dict]:
    """Cards from an API body, de-duplicated by name and in the bank's order."""
    seen: set[str] = set()
    cards: list[dict] = []
    for row in _rows(body):
        card = _card(row)
        if card and card["name"] not in seen:
            seen.add(card["name"])
            cards.append(card)
    return cards


def prompt_block(cards: list[dict]) -> str:
    """The list as text for the answer prompt, debit and credit apart, each card on one line."""
    by_type: dict[str, list[dict]] = {}
    for c in cards:
        by_type.setdefault(c["type"] or "other", []).append(c)
    lines = []
    for kind, group in by_type.items():
        lines.append(f"{kind.capitalize()} cards ({len(group)}):")
        for c in group:
            detail = f" ({c['network']})" if c["network"] else ""
            text = f": {c['description']}" if c["description"] else ""
            lines.append(f"- {c['name']}{detail}{text}")
    return "\n".join(lines)


_SHOWCASE_TYPES = ("debit", "credit", "prepaid")


def _clip(items, count: int, chars: int) -> list[str]:
    return [" ".join(str(i).split())[:chars] for i in (items or []) if str(i).strip()][:count]


def details(card: ProductCard | None) -> dict | None:
    """What the card's details sheet shows, from the knowledge base's own summary of the product (what it is, fees,
    benefits, who may apply, who it suits), trimmed to a size a phone screen can hold. None when there is nothing."""
    if card is None:
        return None
    out = {"summary": " ".join((card.summary or "").split())[:320],
           "fees": _clip(card.fees, 6, 180), "rates": _clip(card.rates, 4, 180),
           "benefits": _clip(card.benefits, 8, 220), "eligibility": _clip(card.eligibility, 6, 180),
           "bestFor": _clip(card.best_for, 6, 60)}
    return {k: v for k, v in out.items() if v} or None


def showcase(cards: list[dict], enriched: list[ProductCard] | None = None) -> list[dict]:
    """The cards as the app draws them (scrollable rows by type): name, type, scheme, what the artwork needs and, when
    the knowledge base describes the card, its details. Types the app has no artwork for are left out of the pictures;
    the text answer still names every card."""
    known = {c.name: c for c in enriched or []}
    shown = []
    for c in cards:
        if c["type"] not in _SHOWCASE_TYPES:
            continue
        item = {"name": c["name"], "type": c["type"], "scheme": c.get("scheme_code") or c["network"].upper(),
                "routingProfile": c.get("routing_profile"), "capabilities": c.get("capabilities") or []}
        extra = details(known.get(c["name"]))
        if extra:
            item["details"] = extra
        shown.append(item)
    return shown[:40]


async def current(jwt: str | None, identity=None) -> list[dict]:
    """The bank's cards now: fetched with the customer's login and kept `LIVE_CARDS_TTL` seconds; without a login,
    the last list kept. Empty when there is none, and the answer then rests on the knowledge base alone."""
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < settings.LIVE_CARDS_TTL:
        return _cache[1]
    if not jwt:
        return _cache[1] if _cache else []
    try:
        result = await CardProductsAdapter().fulfill(identity, jwt, "card_products", None)
        cards = parse(result.data)
    except (AdapterUnavailableError, Exception) as e:  # noqa: BLE001 -- the knowledge base still answers
        logger.warning("live card list unavailable: %s", type(e).__name__)
        return _cache[1] if _cache else []
    if cards:
        _cache = (now, cards)
    return cards


def clear_cache() -> None:
    global _cache
    _cache = None


# ---- the cards a customer can actually ask for ------------------------------------------------------------------------

_APPLY_VIA = {"credit": "credit_card_apply"}     # every other category is requested on the virtual card screen
_CARD_APPLY = "card_apply"


def _words(name: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", name.casefold()))


def merge(stored: list[ProductCard], live: list[dict]) -> list[ProductCard]:
    """The product cards with the bank's live card list applied: the cards a customer can request are exactly the
    live ones, named as the bank names them, each enriched with what the knowledge base says about it (benefits,
    fees, eligibility, who it suits). A stored card that matches no live card is dropped when it is a card product
    (it cannot be requested in the app), and every other product is kept as it is. With no live list nothing changes.

    A stored card matches the live card whose words contain all of its own words, the closest one first ("Visa
    Infinite" is the plain Visa Infinite, not the Islamic one). Words every live name shares (the bank's name, "card")
    say nothing about which card it is, so they are left out of the comparison."""
    if not live:
        return stored
    names = [_words(c["name"]) for c in live]
    shared = {w for w in set().union(*names) if sum(w in n for n in names) >= 0.8 * len(names)}
    live_words = [n - shared for n in names]
    screens = {_CARD_APPLY, *_APPLY_VIA.values()}
    matched: dict[int, ProductCard] = {}
    kept: list[ProductCard] = []
    for card in stored:
        if card.apply_via not in screens:
            kept.append(card)
            continue
        mine = _words(card.name) - shared
        fits = [i for i, w in enumerate(live_words) if mine and mine <= w]
        if fits:
            best = min(fits, key=lambda i: len(live_words[i]) - len(mine))
            matched.setdefault(best, card)
    cards = []
    for i, c in enumerate(live):
        base = matched.get(i)
        kind = f"{c['type']} card" if c["type"] else "card"
        via = _APPLY_VIA.get(c["type"], _CARD_APPLY)
        summary = " ".join(x for x in (c["description"], base.summary if base else "") if x)
        if base:
            cards.append(dataclasses.replace(base, name=c["name"], kind=kind, summary=summary, apply_via=via))
        else:
            cards.append(ProductCard(c["name"], "Cards", kind, summary, apply_via=via))
    return kept + cards
