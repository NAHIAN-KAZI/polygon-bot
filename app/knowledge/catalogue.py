"""The pages and products the knowledge base covers, read from the index itself (T-124).

Nothing here is written by hand: the list is whatever `product` and `group` the uploaded files carry, so a new
product in a re-uploaded file shows up on its own. The query planner shows it to the model so a generic question
("which credit cards do you have?") can be tied to the products of that kind.
"""
from app import vectorstore

_cache: list[dict] | None = None


def distinct(payloads) -> list[dict]:
    """Distinct (name, group) pairs, ordered by group then name so the prompt is stable between calls."""
    seen: dict[tuple[str, str], dict] = {}
    for payload in payloads:
        name, group = payload.get("product"), payload.get("group")
        if name and group:
            seen.setdefault((group, name), {"name": name, "group": group})
    return [seen[key] for key in sorted(seen)]


def load() -> list[dict]:
    global _cache
    if _cache is None:
        _cache = distinct(vectorstore.iter_payloads(["product", "group"]))
    return _cache


def invalidate() -> None:
    """Call after a document is added or removed."""
    global _cache
    _cache = None
