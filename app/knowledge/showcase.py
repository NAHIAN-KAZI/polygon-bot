"""Products as the app draws them (T-171).

Whenever the bot talks about products, the answer also carries the products themselves for the app to show as rows
of pictures: a card is drawn as its artwork (from the bank's live card list), every other product (loan, fixed deposit,
DPS, deposit account...) as a tile with its key facts, and each has a details sheet. Recommendations are ranked and carry
the reasons the bot gave. Everything is taken from data the bot already holds (the product cards and the live list), never
written by the model, and the lists are capped so a payload stays small.
"""
from app.knowledge import live_cards
from app.knowledge.product_cards import ProductCard

_CARD_TYPES = ("debit", "credit", "prepaid")
_MAX_FACT_CHARS = 48
_MAX_ITEMS = 12


def _first_short(items: list[str]) -> str | None:
    for text in items or []:
        text = " ".join(str(text).split())
        if text and len(text) <= _MAX_FACT_CHARS and "schedule of charges" not in text.casefold():
            return text
    return None


def facts(card: ProductCard) -> list[dict]:
    """Up to three short facts for a tile: the minimum, a rate and a fee, only when the product's own text gives them
    briefly."""
    out = []
    if card.minimum and len(card.minimum) <= _MAX_FACT_CHARS:
        out.append({"label": "Minimum", "value": " ".join(card.minimum.split())})
    if rate := _first_short(card.rates):
        out.append({"label": "Rate", "value": rate})
    if fee := _first_short(card.fees):
        out.append({"label": "Fee", "value": fee})
    return out[:3]


def family(card: ProductCard) -> str:
    """The icon family of a tile, from the product's own group heading in the knowledge base."""
    text = f"{card.group} {card.kind}".casefold()
    for word, name in (("loan", "loan"), ("finance", "loan"), ("insurance", "insurance"), ("takaful", "insurance"),
                       ("deposit", "deposit"), ("dps", "deposit"), ("saving", "deposit"), ("account", "deposit")):
        if word in text:
            return name
    return "other"


def item(card: ProductCard, live: list[dict] | None = None, rank: int | None = None, why: list[str] | None = None,
         keep_in_mind: str | None = None) -> dict:
    """One product: a card with its artwork data when the live card list has it, else a tile."""
    out = {"name": card.name, "kind": card.kind, "group": card.group, "rank": rank,
           "why": [w for w in (why or []) if w][:3], "keepInMind": keep_in_mind or None,
           "details": live_cards.details(card)}
    found = next((c for c in live or [] if c["name"] == card.name and c["type"] in _CARD_TYPES), None)
    if found:
        out.update(visual="card", cardType=found["type"], scheme=found.get("scheme_code") or found["network"].upper(),
                   routingProfile=found.get("routing_profile"), capabilities=found.get("capabilities") or [])
    else:
        out.update(visual="tile", family=family(card), facts=facts(card))
    return out


def _section_key(it: dict) -> tuple[int, str]:
    if it["visual"] == "card":
        return (_CARD_TYPES.index(it["cardType"]), it["cardType"])
    return (len(_CARD_TYPES), it.get("group") or "Products")


def build(items: list[dict], ranked: bool = False, title: str | None = None) -> dict | None:
    """The sections the app draws. Ranked picks stay in one row, best first; otherwise debit, credit and prepaid cards
    each get a row and every other product a row per group of the knowledge base."""
    items = items[: _MAX_ITEMS * 3]
    if not items:
        return None
    if ranked:
        return {"ranked": True, "sections": [{"title": title or "Best fit for you", "family": "picks",
                                              "items": items[:_MAX_ITEMS]}]}
    grouped: dict[tuple[int, str], list[dict]] = {}
    for it in items:
        grouped.setdefault(_section_key(it), []).append(it)
    sections = []
    for key in sorted(grouped):
        first = grouped[key][0]
        if first["visual"] == "card":
            sections.append({"title": f"{key[1].capitalize()} cards", "family": key[1], "items": grouped[key][:_MAX_ITEMS]})
        else:
            sections.append({"title": key[1], "family": first.get("family", "other"), "items": grouped[key][:_MAX_ITEMS]})
    return {"ranked": False, "sections": sections}


def by_name(cards: list[ProductCard]) -> dict[str, ProductCard]:
    return {c.name: c for c in cards}
