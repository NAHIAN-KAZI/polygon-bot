"""Bangladesh exchange rates, fetched live and kept only in memory (T-158)."""
import asyncio
import datetime as dt
import json

import pytest

import app.routes.chat as chat_module
from app.banking.routing import RatesQuestion, _rates_question
from app.knowledge import live_rates

from tests.conftest import AUTH_HEADERS

OFFICIAL_BODY = {"rate_date": "2026-10-28", "rates": [
    {"base": "USD", "quote": "BDT", "type": "buy", "value": 123.98},
    {"base": "USD", "quote": "BDT", "type": "reference", "value": 123.98},
    {"base": "USD", "quote": "BDT", "type": "sell", "value": 123.98},
    {"base": "EUR", "quote": "BDT", "type": "buy", "value": 137.8906},
    {"base": "EUR", "quote": "BDT", "type": "sell", "value": 137.9401},
    {"base": "BDT", "quote": "LKR", "type": "buy", "value": 2.68},        # not quoted in taka: left out
    {"base": "XXX", "quote": "BDT", "type": "buy", "value": -1},          # nonsense: left out
]}


@pytest.fixture(autouse=True)
def _fresh_cache():
    live_rates.clear_cache()
    yield
    live_rates.clear_cache()


def fake_sources(monkeypatch, official=OFFICIAL_BODY, market=None, calls=None):
    """`market` maps (code, version) -> bdt rate; a version not listed is a 404 on both hosts."""
    async def get_json(client, url):
        if calls is not None:
            calls.append(url)
        if url == live_rates.settings.RATES_OFFICIAL_URL:
            return official
        for (code, version), rate in (market or {}).items():
            if f"@{version}/" in url and url.endswith(f"/{code.lower()}.json") or url.startswith(f"https://{version}.currency-api") and url.endswith(f"/{code.lower()}.json"):
                return {"date": version if version != "latest" else "2026-10-29", code.lower(): {"bdt": rate}}
        return None
    monkeypatch.setattr(live_rates, "_get_json", get_json)


def test_the_official_table_keeps_only_rows_quoted_in_taka_with_a_single_rate_per_currency():
    table = live_rates._parse_official(OFFICIAL_BODY)
    assert table["published_on"] == "2026-10-28"
    assert set(table["currencies"]) == {"USD", "EUR"}
    assert table["currencies"]["USD"] == {"buy": 123.98, "sell": 123.98, "rate": 123.98}
    assert table["currencies"]["EUR"]["rate"] == pytest.approx(137.91535)


@pytest.mark.parametrize("body", [None, {}, {"rate_date": "2026-10-28", "rates": []}, {"rates": [1]}, "x"])
def test_a_body_that_is_not_a_table_is_no_table(body):
    assert live_rates._parse_official(body) is None


def test_codes_and_periods_are_checked_not_trusted():
    assert live_rates.code_of(" usd ") == "USD" and live_rates.code_of("US") is None and live_rates.code_of("../x") is None
    assert live_rates.clamp_days("7") == 7 and live_rates.clamp_days(99999) == 365 and live_rates.clamp_days(None) == 30
    assert live_rates.clamp_days(0) == 2


def test_the_official_table_is_kept_in_memory_for_a_while_and_a_failure_is_not_cached(monkeypatch):
    calls = []
    fake_sources(monkeypatch, calls=calls)
    first = asyncio.run(live_rates.official())
    assert asyncio.run(live_rates.official()) is first and len(calls) == 1
    live_rates.clear_cache()
    fake_sources(monkeypatch, official=None)
    assert asyncio.run(live_rates.official()) is None


def test_the_trend_is_a_line_of_at_most_thirty_days_with_its_movement(monkeypatch):
    today = dt.date(2026, 10, 29)
    market = {("USD", (today - dt.timedelta(days=d)).isoformat()): 120 + (30 - d) * 0.1 for d in range(1, 31)}
    market[("USD", "latest")] = 123.2
    fake_sources(monkeypatch, market=market)
    line = asyncio.run(live_rates.trend("usd", 30, today=today))
    assert line["currency"] == "USD" and line["days"] == 30
    assert 3 <= len(line["points"]) <= 31 and line["points"] == sorted(line["points"], key=lambda p: p["date"])
    assert line["change_percent"] > 0


def test_too_few_days_is_no_trend_and_a_long_period_is_sampled(monkeypatch):
    calls = []
    fake_sources(monkeypatch, market={("USD", "latest"): 124.0}, calls=calls)
    assert asyncio.run(live_rates.trend("USD", 30)) is None
    live_rates.clear_cache()
    calls.clear()
    fake_sources(monkeypatch, calls=calls)
    asyncio.run(live_rates.trend("USD", 360))
    assert len({u.split("@")[1].split("/")[0] for u in calls if "@" in u}) <= 32      # not 360 requests


def test_a_currency_bangladesh_bank_does_not_print_gets_a_labelled_market_figure(monkeypatch):
    fake_sources(monkeypatch, market={("SAR", "latest"): 33.1})
    data = asyncio.run(live_rates.lookup("sar", 7))
    assert data["focus"]["currency"] == "SAR" and data["focus"]["official_rate"] is None
    assert data["focus"]["market"] == {"date": "2026-10-29", "rate": 33.1}
    assert data["official"]["published_on"] == "2026-10-28"


def test_no_currency_named_shows_usd_and_when_every_source_is_down_there_is_no_data(monkeypatch):
    fake_sources(monkeypatch)
    data = asyncio.run(live_rates.lookup(None, None))
    assert data["focus"]["currency"] == "USD" and data["focus"]["official_rate"]["rate"] == 123.98
    live_rates.clear_cache()
    fake_sources(monkeypatch, official=None)
    assert asyncio.run(live_rates.lookup("USD", 30)) is None


# ---- the reply's facts -------------------------------------------------------------------------------------------------

def outcome_for(monkeypatch, currency=None, days=None, official=OFFICIAL_BODY, market=None):
    fake_sources(monkeypatch, official=official, market=market)
    data = asyncio.run(live_rates.lookup(currency, days))
    return chat_module._rates_outcome(data, RatesQuestion(currency, days))


def test_the_official_rate_is_stated_with_its_date_and_both_buy_and_sell_when_they_differ(monkeypatch):
    out = outcome_for(monkeypatch, "EUR")
    assert out.result_type == "EXCHANGE_RATES" and out.say[0] == "exchange_rates"
    assert "buy 137.8906, sell 137.9401" in out.say[1]["rate"] and "published by Bangladesh Bank on 28 October 2026" in out.say[1]["rate"]
    assert out.say[2] == {"EUR rate": "137.8906"}
    payload = out.result_payload["exchange_rates"]
    assert payload["official"]["source"] == "Bangladesh Bank" and {r["currency"] for r in payload["official"]["rates"]} == {"USD", "EUR"}
    assert payload["attribution"]["url"] == "https://allratestoday.com"


def test_a_market_figure_is_called_indicative_and_not_a_bangladesh_bank_rate(monkeypatch):
    out = outcome_for(monkeypatch, "SAR", market={("SAR", "latest"): 33.1})
    assert "indicative market rate" in out.say[1]["rate"] and "does not publish" in out.say[1]["rate"]
    assert out.result_payload["exchange_rates"]["market"]["rate"] == 33.1


def test_an_unknown_currency_says_none_was_found_and_names_what_is_published(monkeypatch):
    out = outcome_for(monkeypatch, "XYZ")
    assert out.say[1]["not found"] == "no rate was found for XYZ" and out.say[1]["rates Bangladesh Bank publishes"] == "EUR, USD"
    assert out.say[2] == {}


def test_nothing_fetched_is_service_unavailable_never_a_made_up_rate():
    out = chat_module._rates_outcome(None, RatesQuestion())
    assert out.result_type == "SERVICE_UNAVAILABLE" and out.result_payload is None


def test_the_classifier_arguments_are_checked():
    assert _rates_question({"currency": "usd", "days": 7}) == RatesQuestion("USD", 7)
    assert _rates_question({"currency": "dollar", "days": "x"}) == RatesQuestion(None, None)
    assert _rates_question({"days": True}) == RatesQuestion(None, None) and _rates_question(None) == RatesQuestion()


# ---- the chat ------------------------------------------------------------------------------------------------------------

def parse(body):
    out = []
    for block in body.strip("\n").split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            out.append((name, data))
    return out


@pytest.fixture
def rates_chat(monkeypatch):
    seen = {}

    async def classify(message, recent_turns=None, app_notes=None):
        return RatesQuestion("EUR", 7)

    async def lookup(currency, days):
        seen["asked"] = (currency, days)
        return await real_lookup(currency, days)

    real_lookup = live_rates.lookup
    fake_sources(monkeypatch, market={("EUR", "latest"): 137.9})
    monkeypatch.setattr(chat_module, "classify", classify)
    monkeypatch.setattr(chat_module.live_rates_mod, "lookup", lookup)
    monkeypatch.setattr(chat_module.audit, "log_banking_turn", lambda *a, **k: None)
    return seen


def test_a_visitor_who_is_not_signed_in_gets_the_rate_and_the_table(client, rates_chat):
    resp = client.post("/chat", json={"message": "euro rate koto?"}, headers=AUTH_HEADERS)
    events = parse(resp.text)
    result = next(d for n, d in events if n == "result")
    assert result["type"] == "EXCHANGE_RATES" and rates_chat["asked"] == ("EUR", 7)
    assert result["payload"]["exchange_rates"]["official"]["published_on"] == "2026-10-28"
    assert events[-1][0] == "done"
    assert "137.8906" in "".join(d["token"] for n, d in events if n == "token")


def test_the_back_office_switch_turns_the_answer_off_before_anything_is_fetched(client, rates_chat):
    resp = client.post("/chat", json={"message": "euro rate", "disabled_use_cases": ["general.exchange_rates"]},
                       headers=AUTH_HEADERS)
    result = next(d for n, d in parse(resp.text) if n == "result")
    assert result["type"] == "USE_CASE_DISABLED" and "asked" not in rates_chat


def test_the_classifier_turns_a_rates_tool_call_into_a_rates_question(monkeypatch):
    from app.banking import routing

    async def post(messages, **kw):
        return [{"function": {"name": "show_exchange_rates", "arguments": {"currency": "gbp", "days": 14}}}]

    monkeypatch.setattr(routing, "_post_classification", post)
    result = asyncio.run(routing.classify("pound er dam koto, last 2 weeks"))
    assert result == RatesQuestion("GBP", 14)


def test_the_reply_facts_give_dates_in_words_and_the_movement_only_as_a_percent(monkeypatch):
    today = dt.date.today()
    market = {("USD", (today - dt.timedelta(days=d)).isoformat()): 120 + (30 - d) * 0.1 for d in range(1, 31)}
    out = outcome_for(monkeypatch, "USD", market=market)
    assert "28 October 2026" in out.say[1]["rate"] and "2026-10-28" not in out.say[1]["rate"]
    assert out.say[1]["movement"].startswith("the market rate of USD (separate from the published rate above) over the last 30 days: it rose")
    assert "Tk" not in out.say[1]["movement"]


def test_keep_warm_fills_the_official_table_and_the_usd_trend_before_anyone_asks(monkeypatch):
    today = dt.date.today()
    market = {("USD", (today - dt.timedelta(days=d)).isoformat()): 120 + (30 - d) * 0.1 for d in range(1, 31)}
    market[("USD", "latest")] = 123.2
    calls = []
    fake_sources(monkeypatch, market=market, calls=calls)
    sleeps = []

    async def stop_after_one_round(seconds):
        sleeps.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(live_rates.asyncio, "sleep", stop_after_one_round)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(live_rates.keep_warm())
    assert live_rates._official_cache is not None and ("USD", 30) in live_rates._trend_cache
    assert sleeps and 60 <= sleeps[0] < live_rates.settings.RATES_TTL        # woken again before the table goes stale
    calls.clear()
    asyncio.run(live_rates.lookup(None, None))                                # the first question now fetches nothing
    assert calls == []
