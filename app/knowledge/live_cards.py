"""The cards the bank offers right now, from its own card-products API (T-145).

The knowledge base describes cards in pages and passages, and a question like "which credit cards do you have" only
ever sees the few passages that match, so the answer named some cards and then fell back to networks (Visa,
Mastercard). The live list is complete and exact, so it goes into the answer next to the passages: the list says
*which* cards exist, the passages say what each one gives, costs and requires. A new card in the bank's system shows
up here without a code change.

The list is the bank's catalogue, not the customer's data, so it is kept for a few minutes and shared: a visitor who
is not signed in gets the last list a signed-in customer fetched (the endpoint itself needs a login).
"""
import logging
import time

from app.banking.adapters.base import AdapterUnavailableError
from app.banking.adapters.real import CardProductsAdapter
from app.config import settings

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
