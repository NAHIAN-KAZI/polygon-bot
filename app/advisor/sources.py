"""Reads a customer's money data from the bank with their own login (T-130).

One small async function per bank endpoint, all through the adapters' `_call` (same safety checks, same typed
errors, never a raw httpx exception). Bodies come back as plain data, unwrapped from the bank's `data` envelope
when it has one. Nothing here interprets a row: `ledger` and `snapshot` do that.

Errors: `AdapterAuthError` means the login is no longer good and must reach the caller; any other failure
(`AdapterUnavailableError`, `AdapterRejectedError`) loses only that one source, which the snapshot records.
"""
import asyncio
from datetime import date

from app.banking.adapters.base import AdapterAuthError
from app.banking.adapters.real import _call, _is_card_row
from app.config import settings


def _unwrap(body):
    """The bank sometimes wraps a body as {"data": ...}; give back what is inside."""
    return body["data"] if isinstance(body, dict) and isinstance(body.get("data"), (dict, list)) else body


def month_keys(today: date, count: int) -> list[str]:
    """The last `count` calendar months as 'yyyy-MM', the current month first."""
    keys, year, month = [], today.year, today.month
    for _ in range(max(count, 0)):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return keys


async def accounts(jwt: str | None) -> tuple[list[dict], list[dict]]:
    """(deposit accounts, ledger accounts). The account's own `balance` is not the live one; the ledger's is."""
    body = _unwrap(await _call("GET", "/polygon-bank/v1/accounts", jwt))
    body = body if isinstance(body, dict) else {}
    rows = [a for a in body.get("accounts") or [] if isinstance(a, dict)]
    return [a for a in rows if not _is_card_row(a)], [x for x in body.get("ledgerAccounts") or [] if isinstance(x, dict)]


async def transactions(jwt: str | None, account_number: str, start: date, end: date) -> tuple[list[dict], bool]:
    """Rows between two days (inclusive) for one account, newest first, and whether the page cap cut the list
    short. The dates go to the bank as `start` and `end`; the caller still checks each row's own time."""
    rows: list[dict] = []
    truncated = False
    for page in range(settings.ADVISOR_MAX_PAGES):
        body = await _call("GET", "/transfer/v1/accounting/transaction-list", jwt, params={
            "accountNumber": account_number, "start": start.isoformat(), "end": end.isoformat(),
            "page": page, "size": settings.ADVISOR_PAGE_SIZE})
        body = body if isinstance(body, dict) else {}
        rows.extend(r for r in body.get("transactions") or [] if isinstance(r, dict))
        if not (body.get("pagination") or {}).get("hasNext"):
            return rows, False
        truncated = page + 1 >= settings.ADVISOR_MAX_PAGES
    return rows, truncated


async def monthly_summary(jwt: str | None, month: str) -> dict:
    """The bank's own income and spending totals for one month, with spending and income per category."""
    body = _unwrap(await _call("GET", "/report/v1/expense-tracker/summary", jwt, params={"month": month}))
    return body if isinstance(body, dict) else {}


async def monthly_summaries(jwt: str | None, months: list[str], concurrency: int = 6) -> tuple[list[dict], int]:
    """Summaries for many months (oldest first) and how many could not be read. A month that fails is left out,
    so a gap costs that month only. At most `concurrency` months are asked at once: the bank builds each one
    from the customer's ledgers."""
    gate = asyncio.Semaphore(concurrency)

    async def one(month: str) -> dict:
        async with gate:
            return await monthly_summary(jwt, month)

    results = await asyncio.gather(*(one(m) for m in months), return_exceptions=True)
    kept, failed = [], 0
    for month, result in zip(months, results):
        if isinstance(result, AdapterAuthError):
            raise result
        if isinstance(result, BaseException):
            failed += 1
        elif result:
            kept.append({**result, "month": result.get("month") or month})
    return sorted(kept, key=lambda s: s["month"]), failed


async def loans(jwt: str | None) -> list[dict]:
    body = _unwrap(await _call("GET", "/loan/v1/loans", jwt))
    rows = body if isinstance(body, list) else (body.get("loans") if isinstance(body, dict) else None)
    return [r for r in rows or [] if isinstance(r, dict)]


async def deposits(jwt: str | None, path: str) -> list[dict]:
    """The customer's own fixed deposits (`/product/v1/fixed-deposit`) or DPS accounts (`/product/v1/dps`)."""
    body = _unwrap(await _call("GET", path, jwt))
    rows = body if isinstance(body, list) else (body.get("content") or body.get("items") or [] if isinstance(body, dict) else [])
    return [r for r in rows if isinstance(r, dict)]


async def credit_summary(jwt: str | None, card_id: str) -> dict:
    body = _unwrap(await _call("GET", f"/card/v1/cards/{card_id}/credit-summary", jwt))
    return body if isinstance(body, dict) else {}


async def products(jwt: str | None) -> list[dict]:
    """The bank's product catalogue with rates, minimum amounts and tenures (deposits, loans, cards)."""
    body = _unwrap(await _call("GET", "/product/v1/products", jwt))
    rows = body if isinstance(body, list) else (body.get("content") or body.get("products") or [] if isinstance(body, dict) else [])
    return [r for r in rows if isinstance(r, dict)]


def window(today: date, months: int) -> tuple[date, date]:
    """(first day, last day) covering the last `months` calendar months including this one."""
    keys = month_keys(today, months)
    return date(int(keys[-1][:4]), int(keys[-1][5:]), 1), today
