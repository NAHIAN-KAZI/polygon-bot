"""Bangladesh exchange rates, fetched live when a customer asks (T-158).

Two free public sources, neither stored: the rate Bangladesh Bank itself published, as republished by AllRatesToday
(the number the bot states), and dated market snapshots (fawazahmed0's currency-api) that give an indicative trend
line and a market figure for a currency Bangladesh Bank does not print. Everything is kept in memory for a while and
refetched after a restart. A source that fails leaves that part out; nothing is ever invented.
"""
import asyncio
import datetime as dt
import logging
import re
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ATTRIBUTION = {"text": "Exchange rates by AllRatesToday", "url": "https://allratestoday.com"}
_CODE_RE = re.compile(r"^[A-Za-z]{3}$")
_MAX_POINTS = 30
_MAX_DAYS = 365
_MAX_CACHE = 64
_HEADERS = {"User-Agent": "polygon-bank-chatbot/1.0"}

_official_cache: tuple[float, dict] | None = None
_trend_cache: dict[tuple[str, int], tuple[float, dict]] = {}
_latest_cache: dict[str, tuple[float, dict]] = {}


def code_of(raw) -> str | None:
    """A three-letter currency code in upper case, or None."""
    text = str(raw or "").strip()
    return text.upper() if _CODE_RE.match(text) else None


def clamp_days(raw, default: int = 30) -> int:
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return default
    return max(2, min(days, _MAX_DAYS))


def _parse_official(body) -> dict | None:
    """{published_on, currencies: {USD: {buy, sell, rate}}} from the AllRatesToday body; only rows quoted in taka."""
    if not isinstance(body, dict) or not isinstance(body.get("rates"), list) or not body.get("rate_date"):
        return None
    currencies: dict[str, dict] = {}
    for row in body["rates"]:
        if not isinstance(row, dict) or str(row.get("quote") or "").upper() != "BDT":
            continue
        code, kind, value = code_of(row.get("base")), str(row.get("type") or "").lower(), row.get("value")
        if code is None or kind not in ("buy", "sell", "reference") or isinstance(value, bool) \
                or not isinstance(value, (int, float)) or value <= 0:
            continue
        currencies.setdefault(code, {})[kind] = float(value)
    for rates in currencies.values():
        rates["rate"] = rates.get("reference") or round(
            sum(v for k, v in rates.items() if k in ("buy", "sell")) / max(1, sum(k in rates for k in ("buy", "sell"))), 4)
        rates.pop("reference", None)
    return {"published_on": str(body["rate_date"]), "currencies": currencies} if currencies else None


async def _get_json(client: httpx.AsyncClient, url: str):
    try:
        resp = await client.get(url, headers=_HEADERS)
        return resp.json() if resp.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


async def official() -> dict | None:
    """The table Bangladesh Bank last published, or None when it cannot be fetched."""
    global _official_cache
    now = time.monotonic()
    if _official_cache and now - _official_cache[0] < settings.RATES_TTL:
        return _official_cache[1]
    async with httpx.AsyncClient(timeout=settings.RATES_TIMEOUT) as client:
        table = _parse_official(await _get_json(client, settings.RATES_OFFICIAL_URL))
    if table is None:
        logger.warning("official exchange rates unavailable")
        return _official_cache[1] if _official_cache and now - _official_cache[0] < 4 * settings.RATES_TTL else None
    _official_cache = (now, table)
    return table


async def _market_point(client: httpx.AsyncClient, code: str, version: str) -> dict | None:
    """One day's market rate of `code` in taka: {date, rate}, trying the CDN and then its fallback host."""
    for template in (settings.RATES_MARKET_CDN, settings.RATES_MARKET_FALLBACK):
        body = await _get_json(client, template.format(version=version, code=code.lower()))
        rates = body.get(code.lower()) if isinstance(body, dict) else None
        value = rates.get("bdt") if isinstance(rates, dict) else None
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 and body.get("date"):
            return {"date": str(body["date"]), "rate": round(float(value), 4)}
    return None


def _remember(cache: dict, key, value: dict) -> None:
    if len(cache) >= _MAX_CACHE:
        cache.pop(min(cache, key=lambda k: cache[k][0]))
    cache[key] = (time.monotonic(), value)


async def market_latest(code: str) -> dict | None:
    """The latest market rate of `code` in taka, {date, rate}: indicative, not a Bangladesh Bank figure."""
    code = code_of(code)
    if code is None:
        return None
    hit = _latest_cache.get(code)
    if hit and time.monotonic() - hit[0] < settings.RATES_TTL:
        return hit[1]
    async with httpx.AsyncClient(timeout=settings.RATES_TIMEOUT) as client:
        point = await _market_point(client, code, "latest")
    if point:
        _remember(_latest_cache, code, point)
    return point


async def trend(code: str, days: int = 30, today: dt.date | None = None) -> dict | None:
    """The market rate of `code` in taka over the last `days` days as at most 30 points, oldest first, or None when
    fewer than three days could be fetched. Indicative market figures, not Bangladesh Bank's."""
    code = code_of(code)
    if code is None:
        return None
    days = clamp_days(days)
    hit = _trend_cache.get((code, days))
    if hit and time.monotonic() - hit[0] < settings.RATES_TREND_TTL:
        return hit[1]
    today = today or dt.date.today()
    step = max(1, days // _MAX_POINTS)
    versions = [(today - dt.timedelta(days=d)).isoformat() for d in range(days, 0, -step)] + ["latest"]
    gate = asyncio.Semaphore(10)

    async with httpx.AsyncClient(timeout=settings.RATES_TIMEOUT) as client:
        async def one(version: str):
            async with gate:
                return await _market_point(client, code, version)
        points = await asyncio.gather(*(one(v) for v in versions))
    series = sorted({p["date"]: p for p in points if p}.values(), key=lambda p: p["date"])
    if len(series) < 3:
        return None
    first, last = series[0]["rate"], series[-1]["rate"]
    result = {"currency": code, "days": days, "points": series, "change_percent": round((last - first) / first * 100, 2)}
    _remember(_trend_cache, (code, days), result)
    return result


def clear_cache() -> None:
    global _official_cache
    _official_cache = None
    _trend_cache.clear()
    _latest_cache.clear()


async def lookup(currency: str | None, days: int | None) -> dict | None:
    """What a question about the taka's exchange rate needs, or None when no source answered.

    `official` is Bangladesh Bank's published table, `focus` the currency the answer is about (the one named, else USD)
    with its official rate or, when Bangladesh Bank does not print it, a labelled market figure, and `trend` its market
    line over `days`."""
    named = code_of(currency)
    focus = named or "USD"
    table, series = await asyncio.gather(official(), trend(focus, clamp_days(days)))
    row = (table or {}).get("currencies", {}).get(focus)
    market = None
    if row is None and named is not None:
        market = await market_latest(focus)
    if table is None and market is None and series is None:
        return None
    return {"official": table, "focus": {"currency": focus, "named": named is not None, "official_rate": row,
                                         "market": market}, "trend": series}
