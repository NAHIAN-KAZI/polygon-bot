import asyncio
from datetime import date

import pytest

from app.advisor import snapshot, sources
from app.banking.adapters.base import AdapterAuthError, AdapterUnavailableError
from app.banking.identity import CustomerIdentity

TODAY = date(2026, 10, 27)
IDENTITY = CustomerIdentity(customer_id="01711000000")


def tx(day, amount, kind="CREDIT", balance=None, who="X", ttype="TRANSFER"):
    return {"type": kind, "amount": amount, "balance": balance, "txnTime": f"{day}T10:00:00+06:00",
            "fromToAccount": who, "transactionType": ttype}


def summary(month, income, expense, cats):
    return {"month": month, "totalIncome": income, "totalExpense": expense,
            "expenseByCategory": [{"categoryName": n, "amount": a} for n, a in cats.items()]}


HISTORY = [
    summary("2026-06", 9_000_000, 6_000_000, {"Food": 2_000_000, "Rent": 2_500_000, "Transport": 500_000}),
    summary("2026-07", 9_000_000, 6_200_000, {"Food": 2_100_000, "Rent": 2_500_000, "Transport": 600_000}),
    summary("2026-08", 9_000_000, 6_100_000, {"Food": 2_000_000, "Rent": 2_500_000, "Transport": 550_000}),
    summary("2026-09", 9_000_000, 7_500_000, {"Food": 3_500_000, "Rent": 2_500_000, "Transport": 560_000}),
    summary("2026-10", 4_000_000, 1_000_000, {"Food": 600_000}),   # this month, not complete
]
ROWS = [tx(f"2026-{m:02d}-01", 9_000_000, who="EMPLOYER", balance=9_500_000 + m) for m in (6, 7, 8, 9, 10)] + \
       [tx(f"2026-{m:02d}-05", 2_500_000, "DEBIT", who="LANDLORD", balance=7_000_000) for m in (6, 7, 8, 9, 10)] + \
       [tx("2026-10-20", 90_000, "DEBIT", who="Sent to 01799887766 Rahim", ttype="BKASH", balance=6_900_000)]


@pytest.fixture
def bank(monkeypatch):
    state = {"calls": 0, "fail": set(), "cut": False}

    def guard(name):
        state["calls"] += 1
        if name in state["fail"]:
            raise AdapterUnavailableError(f"{name} down")

    async def accounts(jwt):
        guard("accounts")
        return ([{"accountNumber": "1234567890", "accountType": "SAVINGS"}],
                [{"identifier": "1234567890", "balance": 6_900_000}])

    async def transactions(jwt, number, start, end):
        guard("transactions")
        return ROWS, state["cut"]

    async def monthly_summaries(jwt, months, concurrency=6):
        guard("monthly")
        return HISTORY, 0

    async def loans(jwt):
        guard("loans")
        return [{"loanType": "PERSONAL", "emiAmountPoisha": 500_000, "outstandingPrincipalPoisha": 9_000_000,
                 "annualInterestRatePercent": 14, "status": "ACTIVE", "nextDueDate": "2026-11-05"}]

    async def deposits(jwt, path):
        guard(path)
        return [{"id": 1}] if "fixed" in path else []

    async def credit_cards(jwt):
        guard("credit")
        return [{"id": 59, "cardCategory": "CREDIT"}]

    async def credit_summary(jwt, card_id):
        guard("credit summary")
        return {"creditLimit": 10_000_000, "totalOutstanding": 2_500_000, "isOverdue": False}

    async def products(jwt):
        guard("products")
        return []

    monkeypatch.setattr(snapshot.sources, "accounts", accounts)
    monkeypatch.setattr(snapshot.sources, "transactions", transactions)
    monkeypatch.setattr(snapshot.sources, "monthly_summaries", monthly_summaries)
    monkeypatch.setattr(snapshot.sources, "loans", loans)
    monkeypatch.setattr(snapshot.sources, "deposits", deposits)
    monkeypatch.setattr(snapshot.sources, "credit_cards", credit_cards)
    monkeypatch.setattr(snapshot.sources, "credit_summary", credit_summary)
    monkeypatch.setattr(snapshot.sources, "products", products)
    snapshot._cache.clear()
    return state


def build(**kw):
    return asyncio.run(snapshot.build(IDENTITY, "jwt", TODAY, **kw))


def test_facts_report_income_spending_saving_and_the_change_against_earlier_months(bank):
    f = snapshot.facts(build())
    assert f["income"]["average_per_month"] == "Tk 90,000" and f["income"]["steadiness"] == 0.0
    # complete months only: June to September; the unfinished October is reported as month-to-date
    assert f["spending"]["last_complete_month"] == "Tk 75,000"
    assert f["spending"]["change_against_previous_three_months_percent"] == 23.0   # 75,000 against about 61,000
    assert f["spending"]["so_far_this_month"] == "Tk 10,000"
    assert f["saving"]["rate_percent"] == 28.3          # (3.0 + 2.8 + 2.9 + 1.5) of 36.0 lakh poisha
    assert [m["month"] for m in f["monthly"]] == ["2026-06", "2026-07", "2026-08", "2026-09"]


def test_the_category_that_grew_is_visible_with_its_share_and_change(bank):
    cats = {c["name"]: c for c in snapshot.facts(build())["spending_by_category"]}
    assert list(cats)[:2] == ["Rent", "Food"]                       # biggest total first
    assert cats["Food"]["last_complete_month"] == "Tk 35,000" and cats["Food"]["change_percent"] == 72.1
    assert cats["Rent"]["change_percent"] == 0.0 and cats["Rent"]["per_month"] == "Tk 25,000"
    assert cats["Food"]["so_far_this_month"] == "Tk 6,000" and cats["Rent"]["so_far_this_month"] is None
    assert cats["Food"]["per_month"] == "Tk 24,000"                    # June to September only, not the open month


def test_recent_rows_give_payees_rhythm_balances_and_masked_numbers(bank):
    f = snapshot.facts(build())
    assert {r["who"] for r in f["recurring"]} == {"EMPLOYER", "LANDLORD"}
    assert f["main_income_sources"][0]["who"] == "EMPLOYER"
    assert "01799887766" not in str(f)
    assert f["balance"]["latest"] == "Tk 69,000" and f["balance"]["lowest"] and f["balance"]["month_end"]
    assert f["accounts"] == [{"type": "SAVINGS", "ending": "7890", "balance": "Tk 69,000"}]
    assert "1234567890" not in str(f)


def test_holdings_loans_deposits_and_the_credit_card_are_reported(bank):
    f = snapshot.facts(build())
    assert f["loans"][0]["monthly_instalment"] == "Tk 5,000" and f["loans"][0]["still_owed"] == "Tk 90,000"
    assert f["deposit_products_held"] == {"fixed_deposits": 1, "dps": 0}
    assert f["credit_cards"] == [{"limit": "Tk 100,000", "owed": "Tk 25,000", "used_percent": 25.0, "overdue": False}]


def test_coverage_says_what_period_was_read(bank):
    f = snapshot.facts(build())
    assert f["coverage"]["monthly_totals_from"] == "2026-06" and f["coverage"]["months_of_totals"] == 5
    assert f["coverage"]["transactions_from"] == "2026-05-01" and f["coverage"]["could_not_read"] == []
    bank["cut"] = True
    assert snapshot.facts(build())["coverage"]["some_accounts_cut_short"] is True


def test_a_failing_source_loses_only_itself_and_is_named(bank):
    bank["fail"] = {"loans", "monthly"}
    snap = build()
    f = snapshot.facts(snap)
    assert set(snap.missing) == {"loans", "monthly totals"} and "loans" not in f
    assert "spending_by_category" not in f
    assert f["income"]["average_per_month"] == "Tk 90,000"          # still known from the transaction rows
    assert set(f["coverage"]["could_not_read"]) == {"loans", "monthly totals"}


def test_with_no_data_at_all_the_facts_are_just_the_coverage(bank):
    bank["fail"] = {"accounts", "monthly", "loans", "credit", "products", "/product/v1/fixed-deposit", "/product/v1/dps"}
    f = snapshot.facts(build())
    assert set(f) == {"as_of", "coverage"} and "accounts" in f["coverage"]["could_not_read"]


def test_a_lost_login_is_not_swallowed(bank, monkeypatch):
    async def expired(jwt):
        raise AdapterAuthError("expired")

    monkeypatch.setattr(snapshot.sources, "loans", expired)
    with pytest.raises(AdapterAuthError):
        build()


def test_snapshots_are_cached_per_customer_until_forgotten(bank):
    first = asyncio.run(snapshot.get(IDENTITY, "jwt", TODAY))
    calls = bank["calls"]
    assert asyncio.run(snapshot.get(IDENTITY, "jwt", TODAY)) is first and bank["calls"] == calls
    snapshot.forget(IDENTITY)
    assert asyncio.run(snapshot.get(IDENTITY, "jwt", TODAY)) is not first


def test_month_keys_walk_back_across_a_year_end():
    assert sources.month_keys(date(2026, 2, 10), 4) == ["2026-02", "2026-01", "2025-12", "2025-11"]
    assert sources.window(date(2026, 2, 10), 3) == (date(2025, 12, 1), date(2026, 2, 10))


def test_a_credit_card_whose_summary_the_bank_cannot_give_is_named_and_the_rest_still_works(bank):
    bank["fail"] = {"credit summary"}
    snap = build()
    assert snap.missing == ["credit card summary"] and snap.credit == []
    assert "credit_cards" not in snapshot.facts(snap) and snapshot.facts(snap)["income"]


def test_months_before_the_customers_first_activity_do_not_dilute_averages_but_quiet_months_after_it_count(bank):
    quiet = summary("2026-07", 0, 0, {})
    before = [summary("2026-04", 0, 0, {}), summary("2026-05", 0, 0, {})]
    bank_history = before + [HISTORY[0], quiet] + HISTORY[2:]   # June active, July quiet, August on
    snap = build()
    snap.history = bank_history
    f = snapshot.facts(snap)
    assert f["coverage"]["monthly_totals_from"] == "2026-06" and f["coverage"]["months_of_totals"] == 5
    assert [m["month"] for m in f["monthly"]][:2] == ["2026-06", "2026-07"]
    assert f["monthly"][1] == {"month": "2026-07", "in": "Tk 0", "out": "Tk 0", "net": "Tk 0"}
    assert f["income"]["average_per_month"] == "Tk 67,500"    # Tk 90,000 + 0 + 90,000 + 90,000 over the 4 complete months


def test_with_no_activity_anywhere_there_are_no_totals():
    assert snapshot.active_history([summary("2026-05", 0, 0, {}), summary("2026-06", 0, 0, {})]) == []


def test_no_trend_is_reported_from_fewer_than_four_complete_months(bank):
    snap = build()
    snap.history = HISTORY[2:]          # August, September, and the open October: two complete months
    snap.txns = []                      # the rows would add June and July
    f = snapshot.facts(snap)
    assert f["spending"]["change_against_previous_three_months_percent"] is None
    assert all(c["change_percent"] is None for c in f["spending_by_category"])
    assert f["income"]["trend_percent"] is None and f["coverage"]["complete_months"] == 2


def test_what_the_customer_already_has_is_listed_so_advice_does_not_offer_it_again(bank):
    f = snapshot.facts(build())
    assert f["already has"] == {"account types": ["SAVINGS"], "cards": {"debit": 0, "credit": 1},
                                "loans": ["PERSONAL"], "fixed deposits": 1, "DPS accounts": 0}


def test_a_credit_card_is_still_held_when_its_summary_cannot_be_read(bank):
    bank["fail"] = {"credit summary"}
    snap = build()
    assert snap.credit == [] and len(snap.credit_cards) == 1
    assert snapshot.facts(snap)["already has"]["cards"]["credit"] == 1


def test_embedded_debit_cards_and_loan_types_count(bank):
    snap = build()
    snap.accounts = [{"accountNumber": "1", "accountType": "SAVINGS",
                      "cards": [{"cardType": "DEBIT"}, {"cardCategory": "CREDIT"}, "junk"]}]
    held = snapshot.holdings(snap)
    assert held["cards"] == {"debit": 1, "credit": 1} and held["loans"] == ["PERSONAL"]


def _fake_summaries(monkeypatch, active_months, failing=()):
    asked = []

    async def one(jwt, month):
        asked.append(month)
        if month in failing:
            raise AdapterUnavailableError("down")
        busy = month in active_months
        return {"month": month, "totalIncome": 100 if busy else 0, "totalExpense": 50 if busy else 0}

    monkeypatch.setattr(sources, "monthly_summary", one)
    return asked


def test_history_stops_after_an_empty_batch_once_the_customers_activity_has_been_seen(monkeypatch):
    months = sources.month_keys(date(2026, 10, 27), 36)               # 2026-10 back to 2023-11
    asked = _fake_summaries(monkeypatch, active_months={"2026-10", "2026-09", "2026-08"})
    kept, failed = asyncio.run(sources.monthly_summaries("jwt", months, batch=6))
    assert [m["month"] for m in kept][-3:] == ["2026-08", "2026-09", "2026-10"] and failed == 0   # oldest first
    assert len(asked) == 12 and "2023-11" not in asked                 # two batches of six, not all 36


def test_a_whole_quiet_batch_after_activity_ends_the_search_even_if_older_activity_exists(monkeypatch):
    months = sources.month_keys(date(2026, 10, 27), 18)
    active = set(months[0:6]) | set(months[12:18])          # busy, then six quiet months in a row, then older activity
    asked = _fake_summaries(monkeypatch, active_months=active)
    asyncio.run(sources.monthly_summaries("jwt", months, batch=6))
    assert len(asked) == 12                                  # stopped after the quiet batch, as designed


def test_a_quiet_stretch_shorter_than_a_batch_does_not_stop_the_search(monkeypatch):
    months = sources.month_keys(date(2026, 10, 27), 18)
    active = set(months[0:6]) | {months[8]} | set(months[12:18])    # a gap of five quiet months inside one batch
    asked = _fake_summaries(monkeypatch, active_months=active)
    kept, _ = asyncio.run(sources.monthly_summaries("jwt", months, batch=6))
    assert len(asked) == 18 and months[17] in {m["month"] for m in kept}


def test_a_failing_month_never_ends_the_search_early_and_is_counted(monkeypatch):
    months = sources.month_keys(date(2026, 10, 27), 18)
    asked = _fake_summaries(monkeypatch, active_months={months[0]}, failing={months[7]})
    kept, failed = asyncio.run(sources.monthly_summaries("jwt", months, batch=6))
    assert failed == 1 and len(asked) == 18                              # the failed batch could not prove emptiness


def test_a_lost_login_in_the_history_is_raised(monkeypatch):
    async def expired(jwt, month):
        raise AdapterAuthError("expired")

    monkeypatch.setattr(sources, "monthly_summary", expired)
    with pytest.raises(AdapterAuthError):
        asyncio.run(sources.monthly_summaries("jwt", ["2026-10"]))
