"""One customer's money picture, built from their own bank data (T-130, T-135).

`build` reads the sources in `sources` (each failure only loses that part, and is listed in `missing`), computes
every figure with `ledger` and returns a `Snapshot`; `facts` turns it into the compact, already-formatted view the
model is allowed to see. History is tiered so years of data stay cheap:
  recent detail   transaction rows for the last ADVISOR_DETAIL_MONTHS months: payees, rhythm, balance per day
  long history    the bank's own monthly totals and category totals for up to ADVISOR_HISTORY_MONTHS months
The reply must say which periods were covered (`coverage`); nothing is assumed beyond what came back.
"""
import asyncio
import time
from dataclasses import dataclass, field
from datetime import date

from app.advisor import ledger, sources
from app.advisor.money import percent, tk, to_poisha
from app.banking.adapters.base import AdapterAuthError, AdapterUnavailableError
from app.banking.dates import bank_today
from app.banking.identity import CustomerIdentity
from app.config import settings

_cache: dict[str, tuple[float, "Snapshot"]] = {}


@dataclass
class Snapshot:
    as_of: date
    txns: list = field(default_factory=list)              # ledger.Txn rows of the recent detail window
    detail_from: date | None = None
    truncated_accounts: int = 0                           # accounts whose rows were cut short by the page cap
    skipped_rows: int = 0
    history: list[dict] = field(default_factory=list)     # bank monthly summaries, oldest first
    history_requested: int = 0
    accounts: list[dict] = field(default_factory=list)
    ledgers: list[dict] = field(default_factory=list)
    loans: list[dict] = field(default_factory=list)
    fixed_deposits: list[dict] = field(default_factory=list)
    dps: list[dict] = field(default_factory=list)
    credit: list[dict] = field(default_factory=list)      # one summary per credit card that could be read
    catalogue: list[dict] = field(default_factory=list)   # the bank's product catalogue (rates, minimums, tenures)
    missing: list[str] = field(default_factory=list)


async def _soft(name: str, awaitable, missing: list[str], default=None):
    """Await one source; only a lost login escapes, anything else just records that the source is missing."""
    try:
        return await awaitable
    except AdapterAuthError:
        raise
    except Exception:  # noqa: BLE001 -- every other failure costs only this source
        missing.append(name)
        return default


async def _credit(jwt: str | None, missing: list[str], limit: int = 3) -> list[dict]:
    """A summary for each credit card (at most `limit`); a card whose summary cannot be read is named as missing."""
    cards = [c for c in await sources.credit_cards(jwt) if c.get("id")][:limit]
    results = await asyncio.gather(*(sources.credit_summary(jwt, str(c["id"])) for c in cards), return_exceptions=True)
    summaries = []
    for result in results:
        if isinstance(result, AdapterAuthError):
            raise result
        if isinstance(result, BaseException):
            if "credit card summary" not in missing:
                missing.append("credit card summary")
        elif result:
            summaries.append(result)
    return summaries


async def build(identity: CustomerIdentity, jwt: str | None, today: date | None = None) -> Snapshot:
    today = today or bank_today()
    snap = Snapshot(as_of=today)

    accounts, ledgers = await _soft("accounts", sources.accounts(jwt), snap.missing, ([], []))
    snap.accounts, snap.ledgers = accounts, ledgers
    detail_from, _ = sources.window(today, settings.ADVISOR_DETAIL_MONTHS)
    snap.detail_from = detail_from
    history_months = sources.month_keys(today, settings.ADVISOR_HISTORY_MONTHS)
    snap.history_requested = len(history_months)

    async def rows_of(account: dict):
        number = str(account.get("accountNumber") or "")
        rows, cut = await sources.transactions(jwt, number, detail_from, today)
        return number, rows, cut

    (row_sets, summaries, loans, fds, dps, credit, catalogue) = await asyncio.gather(
        _soft("transactions", _gather_rows(accounts, rows_of), snap.missing, []),
        _soft("monthly totals", sources.monthly_summaries(jwt, history_months), snap.missing, ([], 0)),
        _soft("loans", sources.loans(jwt), snap.missing, []),
        _soft("fixed deposits", sources.deposits(jwt, "/product/v1/fixed-deposit"), snap.missing, []),
        _soft("DPS accounts", sources.deposits(jwt, "/product/v1/dps"), snap.missing, []),
        _soft("credit cards", _credit(jwt, snap.missing), snap.missing, []),
        _soft("product catalogue", sources.products(jwt), snap.missing, []),
    )
    for number, rows, cut in row_sets:
        txns, skipped = ledger.parse_rows(rows, number)
        snap.txns.extend(t for t in txns if t.day >= detail_from)
        snap.skipped_rows += skipped
        snap.truncated_accounts += 1 if cut else 0
    snap.history, failed = summaries
    if failed:
        snap.missing.append(f"{failed} of {len(history_months)} monthly totals")
    snap.loans, snap.fixed_deposits, snap.dps, snap.credit, snap.catalogue = loans, fds, dps, credit, catalogue
    return snap


async def _gather_rows(accounts: list[dict], rows_of) -> list:
    results = await asyncio.gather(*(rows_of(a) for a in accounts if a.get("accountNumber")), return_exceptions=True)
    for result in results:
        if isinstance(result, AdapterAuthError):
            raise result
    ok = [r for r in results if not isinstance(r, BaseException)]
    if accounts and not ok:
        raise AdapterUnavailableError("no account's transactions could be read")
    return ok


async def get(identity: CustomerIdentity, jwt: str | None, today: date | None = None) -> Snapshot:
    """A recent snapshot for this customer, rebuilt after ADVISOR_CACHE_SECONDS."""
    key = identity.customer_id
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    snap = await build(identity, jwt, today)
    _cache[key] = (time.monotonic() + settings.ADVISOR_CACHE_SECONDS, snap)
    return snap


def forget(identity: CustomerIdentity) -> None:
    _cache.pop(identity.customer_id, None)


# ---- what the model may see --------------------------------------------------------------------------------------

def active_history(history: list[dict]) -> list[dict]:
    """The monthly summaries from the customer's first month with any money moving. Months before that are not
    quiet months, they are before the customer had any history, so they must not dilute an average. A quiet
    month after it (nothing in, nothing out) is real and stays as a zero."""
    for i, summary in enumerate(history):
        if (to_poisha(summary.get("totalIncome")) or 0) or (to_poisha(summary.get("totalExpense")) or 0):
            return history[i:]
    return []


def _month_totals(snap: Snapshot) -> list[dict]:
    """Income and spending per month: the bank's own totals where it gave them, else computed from the rows."""
    by_month = {m["month"]: {"month": m["month"], "in": to_poisha(m.get("totalIncome")) or 0,
                             "out": to_poisha(m.get("totalExpense")) or 0} for m in active_history(snap.history)}
    for m in ledger.monthly(snap.txns):
        by_month.setdefault(m["month"], {"month": m["month"], "in": m["in"], "out": m["out"]})
    out = []
    for key in sorted(by_month):
        m = by_month[key]
        out.append({**m, "net": m["in"] - m["out"]})
    return out


def averages(snap: Snapshot) -> dict:
    """The figures other code compares with a product's stated requirements, in poisha: average income and
    spending per complete month (None when there is no month at all) and the balance now (None when unknown)."""
    this_month = snap.as_of.strftime("%Y-%m")
    months = _month_totals(snap)
    complete = [m for m in months if m["month"] < this_month] or months
    live = [to_poisha(l.get("balance")) for l in snap.ledgers if l.get("identifier") in
            {str(a.get("accountNumber")) for a in snap.accounts}]
    live = [b for b in live if b is not None]
    stats = ledger.balance_stats(ledger.daily_balance(snap.txns, snap.as_of)) if snap.txns else None
    return {"income": round(sum(m["in"] for m in complete) / len(complete)) if complete else None,
            "spending": round(sum(m["out"] for m in complete) / len(complete)) if complete else None,
            "balance": sum(live) if live else (stats["latest"] if stats else None)}


def categories(history: list[dict], complete_before: str) -> list[dict]:
    """Spending per category over the complete months of the history: total, share of all spending, average per
    month, the last complete month, and how that month compares with the three before it (percent; None when
    there was nothing before). The month still running is reported apart as `so_far_this_month`."""
    series: dict[str, dict[str, int]] = {}
    for summary in history:
        for item in summary.get("expenseByCategory") or []:
            by_month = series.setdefault(str(item.get("categoryName") or "Uncategorised"), {})
            by_month[summary["month"]] = by_month.get(summary["month"], 0) + (to_poisha(item.get("amount")) or 0)
    complete = sorted({s["month"] for s in history if s["month"] < complete_before})
    grand = sum(v for by_month in series.values() for m, v in by_month.items() if m in complete)
    out = []
    for name, by_month in series.items():
        values = [by_month.get(m, 0) for m in complete]
        total = sum(values)
        row = {"name": name, "total": total, "share": percent(total, grand),
               "per_month": round(total / len(complete)) if complete else 0,
               "so_far_this_month": by_month.get(complete_before)}
        if values:
            row["last_complete_month"] = values[-1]
            moved = ledger.change_against_earlier(values)
            row["change_percent"] = moved["change"] if moved else None
        out.append(row)
    return sorted((r for r in out if r["total"] or r["so_far_this_month"]), key=lambda r: -r["total"])


def facts(snap: Snapshot, limit_months: int = 12, limit_categories: int = 8) -> dict:
    """The compact view of the customer given to the model: every amount already formatted, every figure
    computed here. Counterparty text is already masked."""
    this_month = snap.as_of.strftime("%Y-%m")
    months = _month_totals(snap)
    complete = [m for m in months if m["month"] < this_month]
    out: dict = {"as_of": snap.as_of.isoformat()}

    recent = [m for m in complete][-limit_months:]
    history = active_history(snap.history)
    first_history = history[0]["month"] if history else None
    out["coverage"] = {
        "monthly_totals_from": first_history, "months_of_totals": len(history),
        "complete_months": len(complete),
        "transactions_from": snap.detail_from.isoformat() if snap.detail_from else None,
        "transactions_read": len(snap.txns),
        "some_accounts_cut_short": bool(snap.truncated_accounts),
        "could_not_read": snap.missing,
    }

    if months:
        incomes = [m["in"] for m in complete] or [m["in"] for m in months]
        spends = [m["out"] for m in complete] or [m["out"] for m in months]
        out["monthly"] = [{"month": m["month"], "in": tk(m["in"]), "out": tk(m["out"]), "net": tk(m["net"])}
                          for m in recent]
        out["income"] = {"average_per_month": tk(round(sum(incomes) / len(incomes))),
                         "steadiness": ledger.spread(incomes),  # 0 = identical every month
                         "trend_percent": (ledger.change_against_earlier(incomes) or {}).get("change")}
        moved = ledger.change_against_earlier(spends)
        out["spending"] = {
            "average_per_month": tk(round(sum(spends) / len(spends))),
            "average_per_week": tk(round(sum(spends) / len(spends) * 12 / 52)),
            "average_per_day": tk(round(sum(spends) / len(spends) * 12 / 365)),
            "last_complete_month": tk(spends[-1]),
            "change_against_previous_three_months_percent": moved["change"] if moved else None,
            "so_far_this_month": tk(next((m["out"] for m in months if m["month"] == this_month), None)),
        }
        out["saving"] = {"rate_percent": ledger.savings_rate([{"in": m["in"], "net": m["net"]} for m in complete or months])}

    if history:
        cats = categories(history, this_month)
        out["spending_by_category"] = [
            {"name": c["name"], "total": tk(c["total"]), "share_of_spending_percent": c["share"],
             "per_month": tk(c["per_month"]), "last_complete_month": tk(c.get("last_complete_month")),
             "change_percent": c.get("change_percent"), "so_far_this_month": tk(c["so_far_this_month"])}
            for c in cats[:limit_categories]]

    if snap.txns:
        weeks = ledger.weekly(snap.txns)[-8:]
        out["weekly"] = [{"week_of": w["week"], "in": tk(w["in"]), "out": tk(w["out"])} for w in weeks]
        stats = ledger.balance_stats(ledger.daily_balance(snap.txns, snap.as_of))
        if stats:
            out["balance"] = {"latest": tk(stats["latest"]), "average": tk(stats["average"]),
                              "lowest": tk(stats["lowest"]), "highest": tk(stats["highest"]),
                              "days_covered": stats["days"],
                              "month_end": [{"month": m["month"], "balance": tk(m["balance"])}
                                            for m in stats["month_end"][-limit_months:]]}
        out["top_payees"] = [{"who": p["who"], "total": tk(p["total"]), "times": p["count"],
                              "share_of_spending_percent": p["share"]}
                             for p in ledger.top_counterparties(snap.txns, True)]
        out["main_income_sources"] = [{"who": p["who"], "total": tk(p["total"]), "times": p["count"]}
                                      for p in ledger.top_counterparties(snap.txns, False, 4)]
        out["spending_by_payment_type"] = [{"type": k["kind"], "total": tk(k["total"]), "share_percent": k["share"]}
                                           for k in ledger.kind_breakdown(snap.txns, True)]
        out["recurring"] = [{"who": r["who"], "direction": "out" if r["outgoing"] else "in",
                             "typical_amount": tk(r["typical_amount"]), "every_days": r["every_days"],
                             "times_seen": r["occurrences"]} for r in ledger.recurring(snap.txns)[:8]]

    accounts = _held_accounts(snap)
    if accounts:
        out["accounts"] = accounts
    if snap.loans:
        out["loans"] = [{"type": l.get("loanType"), "monthly_instalment": tk(to_poisha(l.get("emiAmountPoisha"))),
                         "still_owed": tk(to_poisha(l.get("outstandingPrincipalPoisha"))),
                         "rate_percent": l.get("annualInterestRatePercent"), "status": l.get("status"),
                         "next_due": l.get("nextDueDate")} for l in snap.loans[:5]]
    if snap.fixed_deposits or snap.dps:
        out["deposit_products_held"] = {"fixed_deposits": len(snap.fixed_deposits), "dps": len(snap.dps)}
    if snap.credit:
        cards = []
        for card in snap.credit:
            limit_, used = to_poisha(card.get("creditLimit")), to_poisha(card.get("totalOutstanding"))
            cards.append({"limit": tk(limit_), "owed": tk(used), "used_percent": percent(used or 0, limit_ or 0),
                          "overdue": bool(card.get("isOverdue"))})
        out["credit_cards"] = cards
    return out


def _held_accounts(snap: Snapshot) -> list[dict]:
    """Each deposit account with its live (ledger) balance; account numbers are masked to the last four."""
    by_identifier = {str(l.get("identifier")): l for l in snap.ledgers}
    held = []
    for a in snap.accounts[:8]:
        number = str(a.get("accountNumber") or "")
        ledger_row = by_identifier.get(number)
        held.append({"type": a.get("accountType") or a.get("accountName"), "ending": number[-4:] if number else None,
                     "balance": tk(to_poisha((ledger_row or {}).get("balance")))})
    return held
