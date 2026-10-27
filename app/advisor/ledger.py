"""What a customer's money did, computed from bank transaction rows (T-130).

Pure functions over plain dicts: no network, no model. Every number a reply quotes comes from here, so the model
never does arithmetic. Amounts stay in poisha until `snapshot` formats them.

A bank row is read as: `type` CREDIT (money in) or DEBIT (money out), `amount` (poisha, positive), `balance` (the
account's balance after the row), `txnTime` (ISO time), `fromToAccount` and `description` (who), `transactionType`
(what kind). A row missing a usable type, amount or time is skipped and counted, never guessed.
"""
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median, pstdev

from app.advisor.money import percent, to_poisha
from app.banking.dates import BANK_TZ
from app.config import settings

_DIGIT_RUN = re.compile(r"\d{6,}")


@dataclass(frozen=True)
class Txn:
    when: datetime          # bank-local (UTC+6)
    amount: int             # poisha, positive
    outgoing: bool
    balance_after: int | None
    account: str
    who: str                # counterparty or description, digit runs masked
    kind: str               # the bank's own transaction type label

    @property
    def day(self) -> date:
        return self.when.date()

    @property
    def month(self) -> str:
        return self.when.strftime("%Y-%m")


def _mask(match: re.Match) -> str:
    digits = match.group()
    return "•" * (len(digits) - 4) + digits[-4:]


def _who(row: dict) -> str:
    text = " ".join(str(row.get("fromToAccount") or row.get("description") or row.get("note") or "").split())
    return _DIGIT_RUN.sub(_mask, text)[:60]


def parse_rows(rows: list, account: str) -> tuple[list[Txn], int]:
    """(readable rows, how many were skipped) for one account."""
    out: list[Txn] = []
    skipped = 0
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            skipped += 1
            continue
        direction = str(row.get("type") or "").upper()
        amount = to_poisha(row.get("amount"))
        raw_time = row.get("txnTime")
        if direction not in ("CREDIT", "DEBIT") or amount is None or not raw_time:
            skipped += 1
            continue
        try:
            when = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        except ValueError:
            skipped += 1
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        out.append(Txn(when.astimezone(BANK_TZ), abs(amount), direction == "DEBIT", to_poisha(row.get("balance")),
                       account, _who(row), str(row.get("transactionType") or "").strip()))
    return out, skipped


def monthly(txns: list[Txn]) -> list[dict]:
    """Money in, out and net per calendar month (bank time), oldest first."""
    months: dict[str, dict] = defaultdict(lambda: {"in": 0, "out": 0, "count": 0})
    for t in txns:
        m = months[t.month]
        m["out" if t.outgoing else "in"] += t.amount
        m["count"] += 1
    return [{"month": k, "in": v["in"], "out": v["out"], "net": v["in"] - v["out"], "count": v["count"]}
            for k, v in sorted(months.items())]


def weekly(txns: list[Txn]) -> list[dict]:
    """Same per week (weeks start on Monday), oldest first; `week` is the Monday's date."""
    weeks: dict[date, dict] = defaultdict(lambda: {"in": 0, "out": 0})
    for t in txns:
        monday = t.day - timedelta(days=t.day.weekday())
        weeks[monday]["out" if t.outgoing else "in"] += t.amount
    return [{"week": k.isoformat(), "in": v["in"], "out": v["out"], "net": v["in"] - v["out"]}
            for k, v in sorted(weeks.items())]


def daily_balance(txns: list[Txn], until: date) -> dict[date, int]:
    """The customer's total balance at the end of each day, from the first day any account has a row to `until`.

    Each account's last row of a day gives its balance that day; days without a row carry the balance forward;
    an account counts from its first row. Accounts whose rows carry no balance are left out."""
    by_account: dict[str, dict[date, int]] = defaultdict(dict)
    for t in sorted(txns, key=lambda t: t.when):
        if t.balance_after is not None:
            by_account[t.account][t.day] = t.balance_after
    if not by_account:
        return {}
    start = min(min(days) for days in by_account.values())
    series: dict[date, int] = {}
    carried = {account: None for account in by_account}
    day = start
    while day <= until:
        for account, days in by_account.items():
            if day in days:
                carried[account] = days[day]
        series[day] = sum(v for v in carried.values() if v is not None)
        day += timedelta(days=1)
    return series


def balance_stats(series: dict[date, int]) -> dict | None:
    """Level of the balance over the covered days, and month-end values; None without a series."""
    if not series:
        return None
    values = list(series.values())
    by_month: dict[str, int] = {}
    for d in sorted(series):
        by_month[d.strftime("%Y-%m")] = series[d]
    return {"latest": values[-1], "average": round(mean(values)), "lowest": min(values), "highest": max(values),
            "days": len(values), "month_end": [{"month": m, "balance": b} for m, b in by_month.items()]}


def top_counterparties(txns: list[Txn], outgoing: bool, limit: int = 8) -> list[dict]:
    """Where money went (or came from) most, by total, with how often and the share of that direction's total."""
    totals: dict[str, dict] = defaultdict(lambda: {"total": 0, "count": 0})
    for t in txns:
        if t.outgoing == outgoing and t.who:
            totals[t.who]["total"] += t.amount
            totals[t.who]["count"] += 1
    grand = sum(v["total"] for v in totals.values())
    ranked = sorted(totals.items(), key=lambda kv: -kv[1]["total"])[:limit]
    return [{"who": who, "total": v["total"], "count": v["count"], "share": percent(v["total"], grand)}
            for who, v in ranked]


def kind_breakdown(txns: list[Txn], outgoing: bool, limit: int = 6) -> list[dict]:
    """Spending (or income) split by the bank's own transaction-type label."""
    totals: dict[str, int] = defaultdict(int)
    for t in txns:
        if t.outgoing == outgoing:
            totals[t.kind or "unlabelled"] += t.amount
    grand = sum(totals.values())
    return [{"kind": k, "total": v, "share": percent(v, grand)}
            for k, v in sorted(totals.items(), key=lambda kv: -kv[1])[:limit]]


def recurring(txns: list[Txn], min_occurrences: int | None = None, interval_spread: float | None = None,
              amount_spread: float | None = None) -> list[dict]:
    """Payments and credits that repeat on a rhythm: the same party, similar amounts, a steady gap between them.

    A group qualifies when it has at least `min_occurrences` rows, the gaps in days vary by less than
    `interval_spread` of their average, and most amounts stay within `amount_spread` of the typical one. This is a
    numeric test on the rows, not a list of names, so a salary, a rent, a loan instalment and a subscription all
    surface the same way. The three limits default to the ADVISOR_RECURRING_* settings."""
    min_occurrences = min_occurrences or settings.ADVISOR_RECURRING_MIN_OCCURRENCES
    interval_spread = interval_spread if interval_spread is not None else settings.ADVISOR_RECURRING_INTERVAL_SPREAD
    amount_spread = amount_spread if amount_spread is not None else settings.ADVISOR_RECURRING_AMOUNT_SPREAD
    groups: dict[tuple[bool, str], list[Txn]] = defaultdict(list)
    for t in txns:
        if t.who:
            groups[(t.outgoing, t.who)].append(t)
    found = []
    for (outgoing, who), items in groups.items():
        if len(items) < min_occurrences:
            continue
        items.sort(key=lambda t: t.when)
        gaps = [(b.day - a.day).days for a, b in zip(items, items[1:])]
        gaps = [g for g in gaps if g > 0]
        if len(gaps) < min_occurrences - 1:
            continue
        average_gap = mean(gaps)
        if average_gap < 5 or pstdev(gaps) > interval_spread * average_gap:
            continue
        typical = median(t.amount for t in items)
        close = sum(1 for t in items if abs(t.amount - typical) <= amount_spread * typical)
        if typical <= 0 or close < 0.7 * len(items):
            continue
        found.append({"who": who, "outgoing": outgoing, "typical_amount": round(typical),
                      "every_days": round(average_gap), "occurrences": len(items), "last_day": items[-1].day.isoformat()})
    return sorted(found, key=lambda r: -r["typical_amount"] * 30 / max(r["every_days"], 1))


def spread(values: list[int]) -> float | None:
    """Coefficient of variation (0 = perfectly steady); None for fewer than two values or a zero average."""
    if len(values) < 2 or mean(values) == 0:
        return None
    return round(pstdev(values) / abs(mean(values)), 2)


def savings_rate(months: list[dict]) -> float | None:
    """Share of income kept over the months given, as a percentage (negative when spending exceeded income)."""
    income = sum(m["in"] for m in months)
    return round(100.0 * sum(m["net"] for m in months) / income, 1) if income > 0 else None


def change_against_earlier(values: list[int], earlier: int = 3) -> dict | None:
    """The latest value against the average of up to `earlier` before it: {'latest', 'earlier_average', 'change'}
    with change in percent (None when the earlier average is zero). None with fewer than two values."""
    if len(values) < 2:
        return None
    before = values[-1 - earlier:-1]
    base = mean(before)
    return {"latest": values[-1], "earlier_average": round(base),
            "change": round(100.0 * (values[-1] - base) / base, 1) if base else None}
