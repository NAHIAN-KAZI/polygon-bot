from datetime import datetime, timezone

import httpx

from app.banking.adapters.base import (
    AdapterAccountSelectionRequiredError,
    AdapterAuthError,
    AdapterResult,
    AdapterUnavailableError,
)
from app.banking.identity import CustomerIdentity
from app.config import settings


async def _call(
    method: str,
    path: str,
    jwt: str | None,
    *,
    params: dict | None = None,
    json: dict | None = None,
) -> dict:
    """Make an authenticated call to the platform API and translate the
    outcome into the adapter's typed exceptions. Never lets a raw httpx
    exception escape."""
    headers = {"Authorization": f"Bearer {jwt}"}
    try:
        async with httpx.AsyncClient(
            base_url=settings.PLATFORM_API_BASE_URL, timeout=30.0
        ) as client:
            response = await client.request(
                method, path, headers=headers, params=params, json=json
            )
    except httpx.HTTPError as exc:
        raise AdapterUnavailableError(f"{method} {path} failed: {exc}") from exc

    if response.status_code in (401, 403):
        raise AdapterAuthError(f"{method} {path} rejected the provided JWT")
    if not response.is_success:
        raise AdapterUnavailableError(
            f"{method} {path} returned {response.status_code}: {response.text}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise AdapterUnavailableError(f"{method} {path} returned non-JSON body") from exc


async def _resolve_account_number(
    customer_identity: CustomerIdentity, jwt: str | None, payload: dict | None,
) -> str:
    """Returns the accountNumber to use. If payload already has one, returns it
    unchanged (no API call — a client that already knows the account skips this
    entirely). Otherwise looks the customer's accounts up via AccountsAdapter:
    0 accounts -> AdapterUnavailableError; 1 -> auto-resolved; 2+ -> raises
    AdapterAccountSelectionRequiredError with a trimmed account list."""
    explicit = (payload or {}).get("accountNumber")
    if explicit:
        return explicit

    result = await accounts_adapter.fulfill(customer_identity, jwt, "accounts", None)
    accounts = result.data.get("data", {}).get("accounts")
    if not isinstance(accounts, list) or len(accounts) == 0:
        raise AdapterUnavailableError("customer has no accounts on record")

    if len(accounts) == 1:
        account_number = accounts[0].get("accountNumber")
        if not account_number:
            raise AdapterUnavailableError("account record missing accountNumber")
        return account_number

    trimmed = [
        {"accountNumber": a.get("accountNumber"), "accountName": a.get("accountName"),
         "accountType": a.get("accountType"), "balance": a.get("balance")}
        for a in accounts
    ]
    raise AdapterAccountSelectionRequiredError(trimmed)


_DATE_RANGE_MAX_PAGES = 10
_DATE_RANGE_MAX_RECORDS = 200
_DATE_RANGE_PAGE_SIZE = 50


async def _fetch_all_pages(
    method: str, path: str, jwt: str | None, base_params: dict, list_key: str,
) -> list:
    """Pages through path (bounded to _DATE_RANGE_MAX_PAGES /
    _DATE_RANGE_MAX_RECORDS, whichever hits first) while pagination.hasNext is
    true, accumulating items found under list_key across all fetched pages."""
    items: list = []
    page = 0
    while page < _DATE_RANGE_MAX_PAGES and len(items) < _DATE_RANGE_MAX_RECORDS:
        body = await _call(
            method, path, jwt,
            params={**base_params, "page": page, "size": _DATE_RANGE_PAGE_SIZE},
        )
        items.extend(body.get(list_key) or [])
        if not (body.get("pagination") or {}).get("hasNext"):
            break
        page += 1
    return items


def _filter_by_date_range(
    items: list, timestamp_key: str, start_date: str, end_date: str,
) -> list:
    """Keeps only items whose timestamp_key falls within [start_date
    00:00:00, end_date 23:59:59] inclusive, both boundaries interpreted as
    UTC. Items missing or with unparseable timestamps are dropped."""
    start_dt = datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(f"{end_date}T23:59:59+00:00")
    filtered = []
    for item in items:
        raw_ts = item.get(timestamp_key)
        if not raw_ts:
            continue
        item_dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        if item_dt.tzinfo is None:
            item_dt = item_dt.replace(tzinfo=timezone.utc)
        if start_dt <= item_dt <= end_dt:
            filtered.append(item)
    return filtered


async def _fetch_and_filter_date_range(
    method: str,
    path: str,
    jwt: str | None,
    base_params: dict,
    list_key: str,
    timestamp_key: str,
    start_date: str,
    end_date: str,
) -> dict:
    items = await _fetch_all_pages(method, path, jwt, base_params, list_key)
    filtered = _filter_by_date_range(items, timestamp_key, start_date, end_date)
    return {list_key: filtered, "pagination": {"totalCount": len(filtered)}, "dateFiltered": True}


class BalanceAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        account_number = await _resolve_account_number(customer_identity, jwt, payload)

        body = await _call(
            "POST",
            "/transfer/v1/accounting/balance",
            jwt,
            json={"accountNumber": account_number},
        )
        balance = body.get("data", {}).get("balance") if isinstance(body.get("data"), dict) else None
        if balance is None:
            balance = body.get("balance")
        return AdapterResult(data={"balance": balance})


class TransactionHistoryAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        payload = payload or {}
        account_number = await _resolve_account_number(customer_identity, jwt, payload)

        start_date = payload.get("startDate")
        end_date = payload.get("endDate")
        if start_date and end_date:
            try:
                data = await _fetch_and_filter_date_range(
                    "GET",
                    "/transfer/v1/accounting/transaction-list",
                    jwt,
                    {"accountNumber": account_number},
                    "transactions",
                    "txnTime",
                    start_date,
                    end_date,
                )
                return AdapterResult(data=data)
            except Exception:
                pass

        body = await _call(
            "GET",
            "/transfer/v1/accounting/transaction-list",
            jwt,
            params={
                "accountNumber": account_number,
                "page": payload.get("page", 0),
                "size": payload.get("size", 10),
            },
        )
        return AdapterResult(data=body)


class AccountsAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        account_id = (payload or {}).get("id")
        path = f"/polygon-bank/v1/accounts/{account_id}" if account_id else "/polygon-bank/v1/accounts"
        body = await _call("GET", path, jwt)
        return AdapterResult(data=body)


class DeviceHistoryAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        body = await _call("GET", "/auth/v1/devices", jwt)
        return AdapterResult(data={"devices": body})


class LoginHistoryAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        payload = payload or {}
        device_id = payload.get("deviceId")
        if not device_id:
            raise AdapterUnavailableError("deviceId is required in payload for login_history")

        start_date = payload.get("startDate")
        end_date = payload.get("endDate")
        if start_date and end_date:
            try:
                data = await _fetch_and_filter_date_range(
                    "GET",
                    f"/auth/v1/devices/{device_id}/login-history",
                    jwt,
                    {},
                    "records",
                    "loginAt",
                    start_date,
                    end_date,
                )
                return AdapterResult(data=data)
            except Exception:
                pass

        body = await _call(
            "GET",
            f"/auth/v1/devices/{device_id}/login-history",
            jwt,
            params={
                "page": payload.get("page", 0),
                "size": payload.get("size", 20),
            },
        )
        return AdapterResult(data=body)


balance_adapter = BalanceAdapter()
transaction_history_adapter = TransactionHistoryAdapter()
accounts_adapter = AccountsAdapter()
device_history_adapter = DeviceHistoryAdapter()
login_history_adapter = LoginHistoryAdapter()

REAL_ADAPTERS = {
    "real:balance": balance_adapter,
    "real:transaction_history": transaction_history_adapter,
    "real:accounts": accounts_adapter,
    "real:device_history": device_history_adapter,
    "real:login_history": login_history_adapter,
}
