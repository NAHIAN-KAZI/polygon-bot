import httpx

from app.banking.adapters.base import AdapterAuthError, AdapterResult, AdapterUnavailableError
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
        async with httpx.AsyncClient(base_url=settings.PLATFORM_API_BASE_URL) as client:
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


class BalanceAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        account_number = (payload or {}).get("accountNumber")
        if not account_number:
            raise AdapterUnavailableError("accountNumber is required in payload for balance")

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
        account_number = payload.get("accountNumber")
        if not account_number:
            raise AdapterUnavailableError(
                "accountNumber is required in payload for transaction_history"
            )

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
        return AdapterResult(data=body)


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
