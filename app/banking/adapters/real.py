import re
from datetime import datetime, timezone

import httpx

from app.banking.adapters.base import (
    AdapterAccountSelectionRequiredError,
    AdapterAuthError,
    AdapterRejectedError,
    AdapterResult,
    AdapterUnavailableError,
    AdapterValidationError,
)
from app.banking.identity import CustomerIdentity
from app.config import settings

# Ids from the request/LLM payload are interpolated into paths (cardId, account id,
# transfer id ...). Only plain segments are allowed, so a value like "../x" or
# "1?admin=true" can never steer the call to another endpoint with the
# customer's JWT.
_SAFE_PATH_RE = re.compile(r"(/[A-Za-z0-9_-]+)+")


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
    if not _SAFE_PATH_RE.fullmatch(path):
        raise AdapterUnavailableError(f"{method} refused: unsafe request path")
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

    bank_message = _extract_error_message(response) if not response.is_success else None
    # A 401 about a verification token (email/mobile change, card actions) is a
    # wrong/expired OTP token, not an expired login.
    if response.status_code == 401 and "verification" in (bank_message or "").lower():
        raise AdapterRejectedError(f"{method} {path} returned 401: {bank_message}", bank_message)
    if response.status_code in (401, 403):
        raise AdapterAuthError(f"{method} {path} rejected the provided JWT")
    if response.status_code in (400, 409, 422, 428) and bank_message:
        raise AdapterRejectedError(
            f"{method} {path} returned {response.status_code}: {bank_message}", bank_message)
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
    if isinstance(accounts, list):
        accounts = [a for a in accounts if not _is_card_row(a)]
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


async def _resolve_ledger_account_identifier(
    customer_identity: CustomerIdentity,
    jwt: str | None,
    payload: dict | None,
    chart_of_account_name: str,
    not_found_message: str,
) -> str:
    """Returns the ledger account `identifier` to use for a product like FD or
    DPS. If payload already has one (under "id" or "identifier"), returns it
    unchanged (no API call). Otherwise looks the customer's accounts up via
    AccountsAdapter, filtering data.ledgerAccounts by chartOfAccountName:
    0 matches -> AdapterUnavailableError(not_found_message); 1 ->
    auto-resolved; 2+ -> raises AdapterAccountSelectionRequiredError with the
    matching accounts (trimmed to identifier/chartOfAccountName)."""
    explicit = (payload or {}).get("id") or (payload or {}).get("identifier")
    if explicit:
        return explicit

    result = await accounts_adapter.fulfill(customer_identity, jwt, "accounts", None)
    ledger_accounts = result.data.get("data", {}).get("ledgerAccounts")
    if not isinstance(ledger_accounts, list):
        ledger_accounts = []
    matches = [a for a in ledger_accounts if a.get("chartOfAccountName") == chart_of_account_name]

    if len(matches) == 0:
        raise AdapterUnavailableError(not_found_message)
    if len(matches) == 1:
        identifier = matches[0].get("identifier")
        if not identifier:
            raise AdapterUnavailableError(
                f"{chart_of_account_name} account record missing identifier"
            )
        return identifier

    trimmed = [
        {"identifier": a.get("identifier"), "chartOfAccountName": a.get("chartOfAccountName")}
        for a in matches
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
            # A customer never knows a device id: gather every enrolled device's
            # recent logins instead (live 2026-10-03, "where was my account logged
            # in from" was answered "service unavailable").
            return AdapterResult(data=await self._all_devices(jwt, payload))

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

    _MAX_DEVICES = 5

    async def _all_devices(self, jwt: str | None, payload: dict) -> dict:
        devices = await _call("GET", "/auth/v1/devices", jwt)
        devices = devices if isinstance(devices, list) else (devices or {}).get("data") or []
        records: list[dict] = []
        for device in [d for d in devices if isinstance(d, dict) and d.get("deviceId")][: self._MAX_DEVICES]:
            body = await _call(
                "GET", f"/auth/v1/devices/{device['deviceId']}/login-history", jwt,
                params={"page": 0, "size": payload.get("size", 10)},
            )
            records.extend(r for r in (body or {}).get("records") or [] if isinstance(r, dict))
        records.sort(key=lambda r: str(r.get("loginAt") or ""), reverse=True)
        return {"records": records[:20], "devicesChecked": min(len(devices), self._MAX_DEVICES)}


class BeneficiaryAdapter:
    # T-38: response shape live-confirmed 2026-09-27 as a bare array (cf.
    # DeviceHistoryAdapter), so it's wrapped the same way.
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        service_type = (payload or {}).get("serviceType")
        params = {"serviceType": service_type} if service_type else None
        body = await _call("GET", "/beneficiary/v1/beneficiaries", jwt, params=params)
        return AdapterResult(data={"beneficiaries": body})


class FeesAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        payload = payload or {}
        transaction_type = payload.get("transactionType")
        amount_taka = payload.get("amount")
        if not transaction_type or amount_taka is None:
            raise AdapterUnavailableError(
                "fee_quote requires payload.transactionType and payload.amount"
            )

        amount_poisha = round(float(amount_taka) * 100)
        body = await _call(
            "GET",
            "/transfer/v1/transaction-type/charge-with-amount",
            jwt,
            params={"appSettingsId": transaction_type, "amount": amount_poisha},
        )
        return AdapterResult(data=body)


class LoansAdapter:
    # T-58: response shape live-confirmed 2026-10-01 as a bare array (cf.
    # DeviceHistoryAdapter/BeneficiaryAdapter), so it's wrapped the same way --
    # the caller (app/routes/chat.py) always calls data.get(...) on the
    # adapter result, which crashes with AttributeError on a bare list.
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        body = await _call("GET", "/loan/v1/loans", jwt)
        data = {"loans": body} if isinstance(body, list) else body
        return AdapterResult(data=data)


class FdProfitHistoryAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        fd_identifier = await _resolve_ledger_account_identifier(
            customer_identity, jwt, payload, "Fixed Deposit", "No Fixed Deposit account found"
        )
        body = await _call(
            "GET", f"/product/v1/fixed-deposit/{fd_identifier}/profit-history", jwt
        )
        data = {"profitHistory": body} if isinstance(body, list) else body
        return AdapterResult(data=data)


class DpsProfitHistoryAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        dps_identifier = await _resolve_ledger_account_identifier(
            customer_identity, jwt, payload, "DPS Deposit", "No DPS account found"
        )
        body = await _call("GET", f"/product/v1/dps/{dps_identifier}/profit-history", jwt)
        data = {"profitHistory": body} if isinstance(body, list) else body
        return AdapterResult(data=data)


class DisputesAdapter:
    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        account_number = await _resolve_account_number(customer_identity, jwt, payload)
        body = await _call(
            "GET",
            "/service-request/v1/disputes",
            jwt,
            params={"accountNumber": account_number},
        )
        data = {"disputes": body} if isinstance(body, list) else body
        return AdapterResult(data=data)


class CardsAdapter:
    """Read-only (T-57). There is no dedicated "list my cards" endpoint in
    the cURL reference -- cards only ever come embedded in each account's
    `cards` array under `GET polygon-bank/v1/accounts` (live-confirmed shape:
    `{"cardNumber": "4001****0251", "cardType": "DEBIT", "id": "41",
    "linkedAccountNumber": "...", "status": "ACTIVE", ...}`). This adapter
    reuses AccountsAdapter rather than inventing a new endpoint call, then
    flattens the `cards` arrays across every account the customer has."""

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        result = await accounts_adapter.fulfill(customer_identity, jwt, "accounts", None)
        accounts = result.data.get("data", {}).get("accounts")
        if not isinstance(accounts, list):
            accounts = []

        cards: list = []
        for account in accounts:
            account_cards = account.get("cards") if isinstance(account, dict) else None
            if isinstance(account_cards, list):
                cards.extend(account_cards)
        return AdapterResult(data={"cards": cards})


_ATTEMPTS_REMAINING_RE = re.compile(r"(\d+)\s+attempt\(s\)\s+remaining", re.IGNORECASE)


def _extract_error_message(response) -> str | None:
    """Best-effort extraction of a human-readable "message" field from a
    non-2xx JSON error body (every documented OTP/freeze error response in
    the bank's contract carries one, e.g. {"message": "Invalid OTP. 2
    attempt(s) remaining."}). Returns None if the body isn't JSON or has no
    such field -- callers must tolerate that and fall back to a generic
    message rather than crashing."""
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, str):
            return message
    return None


def _parse_attempts_remaining(message: str) -> int | None:
    """Parses the bank's documented "Invalid OTP. N attempt(s) remaining."
    wording out of an otp/v1/verify 400 message. Returns None (rather than
    guessing) if the message doesn't match that exact documented pattern."""
    match = _ATTEMPTS_REMAINING_RE.search(message)
    return int(match.group(1)) if match else None


async def send_otp(phone: str) -> None:
    """Calls `POST otp/v1/send` -- public, no JWT -- to trigger an OTP SMS to
    `phone`. Returns None on success; the documented 200 body
    (`{"message": "OTP sent successfully"}`) carries no id/expiry worth
    surfacing.

    *** SECURITY -- do not call with an arbitrary phone number ***
    `phone` must ALWAYS be the phone number embedded in the *customer's own
    verified JWT* -- i.e. `customer_identity.customer_id`, which
    app/banking/identity.py's `verify_jwt` populates from the bank's own
    token-introspection response's "phone" field (CustomerIdentity has no
    separate phone field; customer_id *is* the phone here). This endpoint is
    deliberately unauthenticated (no JWT required to send an OTP), so it is
    the caller's responsibility -- not this function's -- to guarantee the
    phone always comes from that verified identity and never from raw
    request/payload input; otherwise this becomes an SMS bombing primitive
    against arbitrary third-party phone numbers.

    Distinguishes the documented statuses explicitly (this intentionally
    does NOT reuse _call()'s generic 401/403->AdapterAuthError,
    else->AdapterUnavailableError mapping -- none of otp/v1/send's documented
    non-2xx statuses are auth failures, and the conversational layer needs
    to react differently to each):
      - 200 -> returns None.
      - 400 -> AdapterValidationError(reason="INVALID_PHONE") -- malformed or
        missing phone, or a malformed request body.
      - 429 -> AdapterValidationError(reason="SEND_THROTTLED") -- either the
        120s per-phone cooldown or the hourly rate limit (10/hr/IP,
        5/hr/phone). The bank's contract does not document a
        machine-readable retry-after value distinguishing the two, so
        retry_after_seconds is left None rather than guessed.
      - 503 -> AdapterValidationError(reason="SEND_UNAVAILABLE") -- SMS
        gateway down.
      - anything else non-2xx, or a network error/timeout ->
        AdapterUnavailableError (SERVICE_UNAVAILABLE, FR-INTEG-04).

    Dev-mode note (per the task): in dev, OTP is reportedly always "0000",
    not actually sent, with rate limits skipped -- but this function makes
    no assumption about that; it just reports whatever status the platform
    actually returns.
    """
    try:
        async with httpx.AsyncClient(
            base_url=settings.PLATFORM_API_BASE_URL, timeout=30.0
        ) as client:
            response = await client.request(
                "POST", "/otp/v1/send", json={"phone": phone}
            )
    except httpx.HTTPError as exc:
        raise AdapterUnavailableError(f"POST /otp/v1/send failed: {exc}") from exc

    if response.is_success:
        return
    if response.status_code == 400:
        raise AdapterValidationError(
            "INVALID_PHONE",
            _extract_error_message(response) or "Invalid or missing phone number.",
        )
    if response.status_code == 429:
        raise AdapterValidationError(
            "SEND_THROTTLED",
            _extract_error_message(response)
            or "Too many OTP requests for this phone number right now.",
        )
    if response.status_code == 503:
        raise AdapterValidationError(
            "SEND_UNAVAILABLE",
            _extract_error_message(response) or "The SMS gateway is currently unavailable.",
        )
    raise AdapterUnavailableError(
        f"POST /otp/v1/send returned {response.status_code}: {response.text}"
    )


async def verify_otp(phone: str, otp: str) -> str:
    """Calls `POST otp/v1/verify` -- public, no JWT -- and returns the
    `verificationToken` (a UUID string; 10-minute lifetime, single-use,
    consumed by the first protected call that uses it, bound to `phone`) on
    success.

    *** SECURITY -- do not call with an arbitrary phone number ***
    Same constraint as send_otp() above: `phone` must ALWAYS be
    `customer_identity.customer_id` (the phone from the customer's own
    verified JWT), never a caller/payload-supplied value -- the returned
    token is only usable for protected calls authenticated as that same
    phone, so verifying against a different phone than the caller's own JWT
    would produce a token unusable (and misleading) for that caller anyway,
    besides being a needless unauthenticated-endpoint abuse vector.

    Distinguishes the documented statuses explicitly, for the same reason as
    send_otp() above:
      - 200 -> returns body["verificationToken"].
      - 400 -> AdapterValidationError(reason="OTP_INCORRECT",
        attempts_remaining=N) -- wrong code; the bank's own message embeds
        remaining attempts ("Invalid OTP. 2 attempt(s) remaining."), parsed
        best-effort (attempts_remaining is None if the message doesn't match
        that exact documented pattern).
      - 410 -> AdapterValidationError(reason="OTP_EXPIRED") -- no OTP on
        record for this phone (expired after 5 min, already used, or never
        sent) -- the customer needs a fresh send_otp().
      - 429 -> AdapterValidationError(reason="OTP_BLOCKED") -- the 3rd wrong
        attempt blocked this phone for 5 minutes.
      - anything else non-2xx, a network error/timeout, or a 200 body
        missing verificationToken -> AdapterUnavailableError.
    """
    try:
        async with httpx.AsyncClient(
            base_url=settings.PLATFORM_API_BASE_URL, timeout=30.0
        ) as client:
            response = await client.request(
                "POST", "/otp/v1/verify", json={"phone": phone, "otp": otp}
            )
    except httpx.HTTPError as exc:
        raise AdapterUnavailableError(f"POST /otp/v1/verify failed: {exc}") from exc

    if response.is_success:
        try:
            body = response.json()
        except ValueError as exc:
            raise AdapterUnavailableError(
                "POST /otp/v1/verify returned non-JSON body"
            ) from exc
        token = body.get("verificationToken") if isinstance(body, dict) else None
        if not token:
            raise AdapterUnavailableError(
                "POST /otp/v1/verify succeeded but returned no verificationToken"
            )
        return token

    if response.status_code == 400:
        message = _extract_error_message(response) or "Invalid OTP."
        raise AdapterValidationError(
            "OTP_INCORRECT", message, attempts_remaining=_parse_attempts_remaining(message)
        )
    if response.status_code == 410:
        raise AdapterValidationError(
            "OTP_EXPIRED",
            _extract_error_message(response)
            or "No OTP on record for this phone number -- it may have expired, "
            "already been used, or never been sent.",
        )
    if response.status_code == 429:
        raise AdapterValidationError(
            "OTP_BLOCKED",
            _extract_error_message(response)
            or "Too many incorrect OTP attempts -- this phone number is "
            "temporarily blocked.",
        )
    raise AdapterUnavailableError(
        f"POST /otp/v1/verify returned {response.status_code}: {response.text}"
    )


class FreezeCardAdapter:
    """*** MUTATING -- DELIBERATE, NARROW, USER-APPROVED EXCEPTION (T-57) ***
    This is one of only 2 mutating real-platform calls this chatbot has ever
    made (see BeneficiaryAddAdapter below for the other) -- every other real
    adapter in this file is GET-only by standing policy. Do NOT treat this as
    license to add further mutating calls without the same explicit,
    documented user approval.

    Calls `PATCH card/v1/cards/{id}/freeze` (cURL reference section 4.1,
    CONFIRMED against the backend controller/DTO). This adapter only ever
    performs the user-approved conversational flow's *final* step (list
    cards -> ask which -> ask reason -> explicit re-confirmation -> freeze);
    the conversational gathering/confirmation itself lives in
    app/routes/chat.py, owned by a parallel dispatch -- this class is purely
    the data layer that actually executes the call once everything has been
    confirmed.

    Request body (`FreezeCardRequest`), matched exactly to the bank API
    team's supplied contract -- no invented fields:
      - `reasonCode`: enum: the ONLY value documented today is "OTHER", so
        this adapter always sends "OTHER" regardless of payload. A
        customer-given free-text reason (e.g. payload["reason"], gathered
        conversationally) has no corresponding field in this DTO, so it is
        intentionally never forwarded to the real endpoint.
      - `pin` (6-digit PIN) OR `password` (login password) -- EXACTLY ONE,
        never both, never neither (mirrors the live endpoint's own 400
        "Provide exactly one of pin or password" case, so the conversational
        layer gets the same rejection locally instead of a wasted round
        trip). Raises AdapterValidationError(reason=
        "PIN_OR_PASSWORD_REQUIRED") if payload has both or neither.
      - `verificationToken` (required): a UUID obtained from the bank's own
        `POST otp/v1/send` + `POST otp/v1/verify` flow (see send_otp()/
        verify_otp() above). This adapter does not run that OTP flow itself
        -- the caller must supply an already-verified token in
        payload["verificationToken"].

    Freeze-specific error surfacing (distinct from _call()'s generic
    401/403->AdapterAuthError mapping, since both of these are 401s that need
    different customer-facing handling):
      - 401 "Invalid credentials" (wrong PIN/password) ->
        AdapterValidationError(reason="INVALID_CREDENTIALS"). Per the bank's
        contract the verificationToken is NOT consumed on this error, so the
        SAME token can be retried (still within its 10-minute window)
        without resending OTP.
      - 401 "Invalid or expired OTP verification" (token expired, already
        used, or for a different phone) ->
        AdapterValidationError(reason="INVALID_VERIFICATION_TOKEN") -- this
        DOES require a fresh send_otp()+verify_otp().
      - any other 401/403, or the response body doesn't match either
        documented message -> generic AdapterAuthError (unchanged fallback).

    payload["cardId"] (or payload["id"]) is required -- raises
    AdapterUnavailableError if missing, never guesses which card.
    """

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        payload = payload or {}
        card_id = payload.get("cardId") or payload.get("id")
        if not card_id:
            raise AdapterUnavailableError(
                "cardId (or id) is required in payload to freeze a card"
            )

        verification_token = payload.get("verificationToken")
        if not verification_token:
            raise AdapterUnavailableError(
                "verificationToken is required in payload to freeze a card"
            )

        pin = payload.get("pin")
        password = payload.get("password")
        if bool(pin) == bool(password):  # both truthy, or both falsy/missing
            raise AdapterValidationError(
                "PIN_OR_PASSWORD_REQUIRED", "Provide exactly one of pin or password"
            )

        body = {"reasonCode": "OTHER", "verificationToken": verification_token}
        if pin:
            body["pin"] = pin
        else:
            body["password"] = password

        path = f"/card/v1/cards/{card_id}/freeze"
        headers = {"Authorization": f"Bearer {jwt}"}
        try:
            async with httpx.AsyncClient(
                base_url=settings.PLATFORM_API_BASE_URL, timeout=30.0
            ) as client:
                response = await client.request("PATCH", path, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise AdapterUnavailableError(f"PATCH {path} failed: {exc}") from exc

        if response.status_code in (401, 403):
            message = (_extract_error_message(response) or "").lower()
            if "invalid or expired otp" in message:
                raise AdapterValidationError(
                    "INVALID_VERIFICATION_TOKEN",
                    "The OTP verification token is invalid or expired -- a fresh "
                    "OTP send and verify is needed.",
                )
            if "invalid credentials" in message:
                raise AdapterValidationError(
                    "INVALID_CREDENTIALS",
                    "The PIN or password provided was incorrect.",
                )
            raise AdapterAuthError(f"PATCH {path} rejected the provided JWT")
        if not response.is_success:
            raise AdapterUnavailableError(
                f"PATCH {path} returned {response.status_code}: {response.text}"
            )

        try:
            result = response.json()
        except ValueError as exc:
            raise AdapterUnavailableError(f"PATCH {path} returned non-JSON body") from exc

        data = result if isinstance(result, dict) else {"result": result}
        return AdapterResult(data=data)


class BeneficiaryAddAdapter:
    """*** MUTATING -- DELIBERATE, NARROW, USER-APPROVED EXCEPTION (T-60) ***
    This is one of only 2 mutating real-platform calls this chatbot has ever
    made (see FreezeCardAdapter above for the other) -- every other real
    adapter in this file, including BeneficiaryAdapter's own list operation
    just above (left completely unchanged by this class), is GET-only by
    standing policy. Do NOT treat this as license to add further mutating
    calls without the same explicit, documented user approval.

    Calls `POST beneficiary/v1/beneficiaries` (cURL reference section 14.20,
    CONFIRMED, `201 Created`). Registered under the distinct subservice id
    `beneficiary_add` rather than reusing `beneficiary` (the existing list
    operation's id, untouched).

    Request body (`CreateBeneficiaryRequest`), matched exactly to the doc:
      - `serviceType` (required enum, same values as the list endpoint's
        `serviceType` filter) and `nickname` (required) -- raises
        AdapterUnavailableError if either is missing, never guesses.
      - The remaining fields (`identifierType`, `accountNumber`,
        `accountHolderName`, `bankName`, `branchName`, `district`,
        `routingNumber`, `mfsProvider`, `providerId`) are all optional and
        type-dependent (which combination is required for a given
        serviceType is enforced server-side, not by this DTO, per the doc) --
        forwarded only if present in payload, never invented or defaulted.
    """

    _OPTIONAL_FIELDS = (
        "identifierType",
        "accountNumber",
        "accountHolderName",
        "bankName",
        "branchName",
        "district",
        "routingNumber",
        "mfsProvider",
        "providerId",
    )

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        payload = payload or {}
        service_type = payload.get("serviceType")
        nickname = payload.get("nickname")
        if not service_type or not nickname:
            raise AdapterUnavailableError(
                "serviceType and nickname are both required in payload to add a beneficiary"
            )

        body = {"serviceType": service_type, "nickname": nickname}
        for field in self._OPTIONAL_FIELDS:
            if payload.get(field) is not None:
                body[field] = payload[field]

        result = await _call("POST", "/beneficiary/v1/beneficiaries", jwt, json=body)
        data = result if isinstance(result, dict) else {"result": result}
        return AdapterResult(data=data)


# --- T-64: read-only (GET) adapters for 17 additional services ---------------
#
# Every endpoint below was matched against its section of
# planning/input/Internet Banking API cURL Reference.md (section number in each
# class docstring) and live-verified against the dev platform on 2026-10-03.
# All are GET-only. Any bare-array response is wrapped under a named key via
# _wrap_list(): app/routes/chat.py always calls data.get(...) on an adapter
# result and crashes with AttributeError on a bare list.


def _wrap_list(body, key: str) -> dict:
    """Returns body unchanged if it's already a dict; otherwise wraps it as
    {key: body}. Live-confirmed bare-array endpoints (complaints,
    profile-changes, contact-priority) need this, and it is applied
    defensively to every T-64 adapter in case another one changes shape."""
    return body if isinstance(body, dict) else {key: body}


def _forward_present(payload: dict, keys: tuple[str, ...]) -> dict | None:
    """Builds a query-param dict from only those `keys` actually present
    (non-None) in payload -- never invents or defaults a value."""
    params = {k: payload[k] for k in keys if payload.get(k) is not None}
    return params or None


def _is_card_row(account: object) -> bool:
    """Since 2026-10-04 the bank also lists linked credit/prepaid cards as rows of
    GET polygon-bank/v1/accounts (id "card-<n>", balance "0"). They aren't deposit
    accounts: never offer them as "which account?" or call account endpoints with them."""
    return isinstance(account, dict) and (
        str(account.get("id") or "").startswith("card-")
        or str(account.get("accountType") or "").upper() in ("CREDIT", "PREPAID")
    )


async def _list_customer_accounts(customer_identity: CustomerIdentity, jwt: str | None) -> list:
    result = await accounts_adapter.fulfill(customer_identity, jwt, "accounts", None)
    data = result.data.get("data") if isinstance(result.data, dict) else None
    accounts = data.get("accounts") if isinstance(data, dict) else None
    return [a for a in accounts if not _is_card_row(a)] if isinstance(accounts, list) else []


async def _resolve_account_id(
    customer_identity: CustomerIdentity, jwt: str | None, payload: dict | None,
) -> str:
    """Returns the *internal numeric account id* (the `id` field of each
    entry in GET polygon-bank/v1/accounts, e.g. "74" -- NOT the account
    number; cURL reference 13.2 "id (Long, internal account ID)").

    payload["id"] -> used as-is, no lookup. payload["accountNumber"] (what a
    client re-sends after an ACCOUNT_SELECTION_REQUIRED round trip) -> mapped
    to that account's id via the accounts list. Otherwise: 0 accounts ->
    AdapterUnavailableError; 1 -> auto; 2+ -> AdapterAccountSelectionRequiredError
    (entries carry both id and accountNumber so either can be sent back)."""
    payload = payload or {}
    explicit = payload.get("id")
    if explicit:
        return str(explicit)

    accounts = await _list_customer_accounts(customer_identity, jwt)
    if not accounts:
        raise AdapterUnavailableError("customer has no accounts on record")

    wanted_number = payload.get("accountNumber")
    if wanted_number:
        for a in accounts:
            if isinstance(a, dict) and str(a.get("accountNumber")) == str(wanted_number):
                if not a.get("id"):
                    raise AdapterUnavailableError("account record missing id")
                return str(a["id"])
        raise AdapterUnavailableError("accountNumber not found among customer's accounts")

    if len(accounts) == 1:
        account_id = accounts[0].get("id") if isinstance(accounts[0], dict) else None
        if not account_id:
            raise AdapterUnavailableError("account record missing id")
        return str(account_id)

    trimmed = [
        {"id": a.get("id"), "accountNumber": a.get("accountNumber"),
         "accountName": a.get("accountName"), "accountType": a.get("accountType"),
         "balance": a.get("balance")}
        for a in accounts if isinstance(a, dict)
    ]
    raise AdapterAccountSelectionRequiredError(trimmed)


def _is_credit_card(card: dict) -> bool:
    # cards_adapter's entries (embedded in GET polygon-bank/v1/accounts) carry
    # the category in `cardType` (live: "DEBIT"). The standalone card list
    # (GET card/v1/cards) uses `cardCategory` for the same thing and reuses
    # `cardType` for PHYSICAL/VIRTUAL -- so accept either field. The exact
    # "CREDIT" literal is unconfirmed live: the test customer has no credit
    # card (2026-10-03); the platform's own 422 message is "Card is not a
    # CREDIT card", which is the best available evidence for the spelling.
    return "CREDIT" in (
        str(card.get("cardType") or "").upper(),
        str(card.get("cardCategory") or "").upper(),
    )


async def _resolve_credit_card_id(
    customer_identity: CustomerIdentity, jwt: str | None, payload: dict | None,
) -> str:
    """payload["cardId"] -> used as-is. Otherwise lists the customer's cards
    via cards_adapter and keeps only credit cards: 0 ->
    AdapterUnavailableError("No credit card found"); 1 -> auto; 2+ ->
    AdapterAccountSelectionRequiredError with card-shaped entries
    (id/cardNumber/cardType/status -- chat.py's _describe_selection_account
    renders cardType/cardNumber)."""
    explicit = (payload or {}).get("cardId")
    if explicit:
        return str(explicit)

    # Credit cards aren't linked to a deposit account, so they never appear in
    # /polygon-bank/v1/accounts' embedded cards[] -- list them from
    body = await _call("GET", "/card/v1/cards", jwt)
    # Live shape: {"status": "success", "data": {"cards": [...]}} (CardController).
    data = body.get("data") if isinstance(body, dict) else body
    cards = data.get("cards") if isinstance(data, dict) else data
    credit_cards = [c for c in (cards or []) if isinstance(c, dict) and _is_credit_card(c)]

    if not credit_cards:
        raise NoCreditCardError("No credit card found")
    if len(credit_cards) == 1:
        card_id = credit_cards[0].get("id")
        if not card_id:
            raise AdapterUnavailableError("credit card record missing id")
        return str(card_id)

    # card/v1/cards returns FULL card numbers -- mask before anything leaves here.
    trimmed = [
        {"id": c.get("id"),
         "cardNumber": "****" + str(c.get("cardNumber") or "")[-4:],
         "cardType": c.get("cardCategory") or c.get("cardType"),
         "status": c.get("status")}
        for c in credit_cards
    ]
    raise AdapterAccountSelectionRequiredError(trimmed)


class _SimpleGetAdapter:
    """A parameterless (or fixed-params) GET whose body is returned as-is,
    with a bare-array body wrapped under `list_key`."""

    def __init__(self, path: str, list_key: str):
        self.path = path
        self.list_key = list_key

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        body = await _call("GET", self.path, jwt)
        return AdapterResult(data=_wrap_list(body, self.list_key))


class _PagedGetAdapter:
    """GET with page/size taken from payload, falling back to the defaults the
    cURL reference documents for that endpoint."""

    def __init__(self, path: str, list_key: str, default_size: int):
        self.path = path
        self.list_key = list_key
        self.default_size = default_size

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        payload = payload or {}
        params = {
            "page": payload.get("page", 0),
            "size": payload.get("size", self.default_size),
        }
        body = await _call("GET", self.path, jwt, params=params)
        return AdapterResult(data=_wrap_list(body, self.list_key))


class AccountTransactionsAdapter:
    """GET polygon-bank/v1/accounts/{id}/transactions (cURL 13.2). `{id}` is
    the internal numeric account id, not the account number; no query params
    (the controller takes no paging/date range). Live shape:
    {"data": {"transactions": [...]}, "status": "success"}."""

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        account_id = await _resolve_account_id(customer_identity, jwt, payload)
        body = await _call("GET", f"/polygon-bank/v1/accounts/{account_id}/transactions", jwt)
        return AdapterResult(data=_wrap_list(body, "transactions"))


class CardProductsAdapter:
    """GET card/v1/card-products (cURL 4.10). Optional filters cardCategory,
    scheme, domesticNetwork, internationalNetwork are forwarded only if
    present in payload."""

    _FILTERS = ("cardCategory", "scheme", "domesticNetwork", "internationalNetwork")

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        params = _forward_present(payload or {}, self._FILTERS)
        body = await _call("GET", "/card/v1/card-products", jwt, params=params)
        return AdapterResult(data=_wrap_list(body, "cardProducts"))


class NoCreditCardError(AdapterUnavailableError):
    """The customer simply has no credit card -- a real answer, not an outage."""


# What the credit-card adapters return instead of failing, so the reply can say
# "you don't have a credit card" rather than "service unavailable".
_NO_CREDIT_CARD = {"creditCard": None, "answer": "You don't have a credit card with Polygon Bank."}


class CreditCardSummaryAdapter:
    """GET card/v1/cards/{id}/credit-summary (cURL 6.2). `{id}` is the numeric
    card id. Live: a non-credit card id returns 422 "Card is not a CREDIT
    card" (-> AdapterUnavailableError)."""

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        try:
            card_id = await _resolve_credit_card_id(customer_identity, jwt, payload)
        except NoCreditCardError:
            return AdapterResult(data=dict(_NO_CREDIT_CARD))
        body = await _call("GET", f"/card/v1/cards/{card_id}/credit-summary", jwt)
        return AdapterResult(data=_wrap_list(body, "creditSummary"))


class CreditCardStatementAdapter:
    """GET card/v1/cards/{id}/statements (cURL 13.3). The doc marks `isBilled`
    (boolean) and `month` (yyyy-MM) as REQUIRED, but per T-64 they are only
    forwarded if present in payload -- never invented. Live (2026-10-03):
    omitting them returns a 500 "An internal error occurred" from the
    platform (-> AdapterUnavailableError)."""

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        payload = payload or {}
        try:
            card_id = await _resolve_credit_card_id(customer_identity, jwt, payload)
        except NoCreditCardError:
            return AdapterResult(data=dict(_NO_CREDIT_CARD))
        # Both params are required by the platform (500 without them); when the
        # customer didn't specify, default to the current month's unbilled view.
        is_billed = payload.get("isBilled", False)
        params = {
            "isBilled": (
                ("true" if is_billed else "false") if isinstance(is_billed, bool)
                else str(is_billed).lower()
            ),
            "month": payload.get("month") or datetime.now(timezone.utc).strftime("%Y-%m"),
        }
        body = await _call("GET", f"/card/v1/cards/{card_id}/statements", jwt, params=params)
        return AdapterResult(data=_wrap_list(body, "statements"))


class EmailTransfersAdapter:
    """List: GET transfer/v1/email-transfer (cURL 14.10) -- `tab`, `page`,
    `size` forwarded only if present in payload (server defaults: pending/0/10).
    Detail: if payload["id"] is given, GET transfer/v1/email-transfer/{id}
    (cURL 14.11) instead."""

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        payload = payload or {}
        transfer_id = payload.get("id")
        if transfer_id:
            body = await _call("GET", f"/transfer/v1/email-transfer/{transfer_id}", jwt)
            return AdapterResult(data=_wrap_list(body, "emailTransfer"))
        params = _forward_present(payload, ("tab", "page", "size"))
        body = await _call("GET", "/transfer/v1/email-transfer", jwt, params=params)
        return AdapterResult(data=_wrap_list(body, "items"))


class TransferLimitAdapter:
    """GET transfer/v1/my-limit/{accountIdentifier} (cURL 14.27);
    accountIdentifier is the account number (String), resolved via
    _resolve_account_number."""

    async def fulfill(
        self,
        customer_identity: CustomerIdentity,
        jwt: str | None,
        subservice: str,
        payload: dict | None,
    ) -> AdapterResult:
        account_number = await _resolve_account_number(customer_identity, jwt, payload)
        body = await _call("GET", f"/transfer/v1/my-limit/{account_number}", jwt)
        return AdapterResult(data=_wrap_list(body, "limits"))


# --- T-75: customer-requested changes (*** MUTATING, user-approved 2026-10-04 ***) --
# Never called on a first message: the chat layer only reaches these after an
# explicit "yes" (complaint/nickname/address) or a verified OTP (email/mobile).

COMPLAINT_CATEGORIES = (
    "ACCOUNT", "CARD", "TRANSACTION", "LOAN_DEPOSIT", "MOBILE_APP_TECHNICAL", "SERVICE_QUALITY", "OTHER",
)
ADDRESS_FIELDS = ("presentAddress", "permanentAddress", "district", "division")


def _required(payload: dict | None, *fields: str) -> dict:
    payload = payload or {}
    missing = [f for f in fields if not payload.get(f)]
    if missing:
        raise AdapterUnavailableError(f"missing required payload fields: {', '.join(missing)}")
    return payload


async def lookup_recipient(jwt: str | None, identifier: str) -> dict | None:
    """GET polygon-bank/v1/accounts/recipient/{identifier} (added 2026-10-04): the
    Polygon Bank account behind an account/card/mobile number -> {accountNumber,
    accountName}. None when it isn't a Polygon Bank account (404)."""
    digits = re.sub(r"\D", "", str(identifier or ""))
    if not digits:
        return None
    try:
        body = await _call("GET", f"/polygon-bank/v1/accounts/recipient/{digits}", jwt)
    except AdapterRejectedError:
        return None
    except AdapterUnavailableError as exc:
        if " returned 404" in str(exc):
            return None
        raise
    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) and data.get("accountNumber") else None


class SubmitComplaintAdapter:
    """POST support/v1/complaints (cURL 3.5/8.4): {category (enum), description (<=2000)}."""

    async def fulfill(self, customer_identity, jwt, subservice, payload) -> AdapterResult:
        payload = _required(payload, "category", "description")
        category = payload["category"] if payload["category"] in COMPLAINT_CATEGORIES else "OTHER"
        body = await _call("POST", "/support/v1/complaints", jwt,
                           json={"category": category, "description": str(payload["description"])[:2000]})
        return AdapterResult(data=body if isinstance(body, dict) else {"result": body})


class UpdateNicknameAdapter:
    """PATCH auth/v1/user/profile/nickname (cURL 7.2): {nickName} -- capital N."""

    async def fulfill(self, customer_identity, jwt, subservice, payload) -> AdapterResult:
        payload = _required(payload, "nickName")
        body = await _call("PATCH", "/auth/v1/user/profile/nickname", jwt,
                           json={"nickName": str(payload["nickName"]).strip()})
        return AdapterResult(data=body if isinstance(body, dict) else {"result": body})


class UpdateAddressAdapter:
    """PATCH customer/v1/me/demographic (cURL 7.8), partial update: only the
    address fields the customer gave are sent."""

    async def fulfill(self, customer_identity, jwt, subservice, payload) -> AdapterResult:
        fields = {k: str(v).strip() for k, v in (payload or {}).items() if k in ADDRESS_FIELDS and v}
        if not fields:
            raise AdapterUnavailableError("no address field given")
        body = await _call("PATCH", "/customer/v1/me/demographic", jwt, json=fields)
        return AdapterResult(data=body if isinstance(body, dict) else {"result": body})


class UpdateEmailAdapter:
    """POST auth/v1/auth/email/update (cURL 7.6): {newEmail, verificationToken}."""

    async def fulfill(self, customer_identity, jwt, subservice, payload) -> AdapterResult:
        payload = _required(payload, "newEmail", "verificationToken")
        body = await _call("POST", "/auth/v1/auth/email/update", jwt,
                           json={"newEmail": payload["newEmail"], "verificationToken": payload["verificationToken"]})
        return AdapterResult(data=body if isinstance(body, dict) else {"result": body})


class UpdateMobileAdapter:
    """POST auth/v1/auth/mobile/update (cURL 7.5): {newPhone (^01[3-9]\\d{8}$),
    verificationToken}. The bank binds the token to the customer's CURRENT phone
    (UserAuthServiceImpl.updateMobile), so the OTP goes there, not to newPhone."""

    async def fulfill(self, customer_identity, jwt, subservice, payload) -> AdapterResult:
        payload = _required(payload, "newPhone", "verificationToken")
        body = await _call("POST", "/auth/v1/auth/mobile/update", jwt,
                           json={"newPhone": payload["newPhone"], "verificationToken": payload["verificationToken"]})
        return AdapterResult(data=body if isinstance(body, dict) else {"result": body})


balance_adapter = BalanceAdapter()
transaction_history_adapter = TransactionHistoryAdapter()
accounts_adapter = AccountsAdapter()
device_history_adapter = DeviceHistoryAdapter()
login_history_adapter = LoginHistoryAdapter()
beneficiary_adapter = BeneficiaryAdapter()
fees_adapter = FeesAdapter()
loans_adapter = LoansAdapter()
fd_profit_history_adapter = FdProfitHistoryAdapter()
dps_profit_history_adapter = DpsProfitHistoryAdapter()
disputes_adapter = DisputesAdapter()
cards_adapter = CardsAdapter()
freeze_card_adapter = FreezeCardAdapter()
beneficiary_add_adapter = BeneficiaryAddAdapter()

# T-64 (all GET, read-only).
complaints_adapter = _SimpleGetAdapter("/support/v1/complaints", "complaints")  # 3.6
account_transactions_adapter = AccountTransactionsAdapter()  # 13.2
card_limit_requests_adapter = _SimpleGetAdapter(
    "/card/v1/cards/limit-change-requests", "requests"
)  # 4.8
card_products_adapter = CardProductsAdapter()  # 4.10
virtual_card_requests_adapter = _PagedGetAdapter(
    "/card/v1/cards/virtual/requests", "requests", default_size=10
)  # 4.16
replacement_requests_adapter = _SimpleGetAdapter(
    "/card/v1/cards/replacement-requests", "requests"
)  # 5.1
credit_card_summary_adapter = CreditCardSummaryAdapter()  # 6.2
credit_card_statement_adapter = CreditCardStatementAdapter()  # 13.3
profile_adapter = _SimpleGetAdapter("/auth/v1/user", "profile")  # 7.1
address_adapter = _SimpleGetAdapter("/customer/v1/me/demographic", "address")  # 7.7
contacts_adapter = _SimpleGetAdapter("/customer/v1/me/contacts", "contacts")  # 7.10
profile_change_requests_adapter = _SimpleGetAdapter(
    "/service-request/v1/profile-changes", "requests"
)  # 7.12
contact_priority_requests_adapter = _SimpleGetAdapter(
    "/service-request/v1/contact-priority", "requests"
)  # 7.14
gifts_received_adapter = _SimpleGetAdapter(
    "/transfer/v1/bank-transfer/gift/received", "items"
)  # 14.6
email_transfers_adapter = EmailTransfersAdapter()  # 14.10 / 14.11
qr_payment_history_adapter = _PagedGetAdapter(
    "/merchant/v1/qr/history", "payments", default_size=20
)  # 14.18
transfer_limit_adapter = TransferLimitAdapter()  # 14.27

REAL_ADAPTERS = {
    "real:balance": balance_adapter,
    "real:transaction_history": transaction_history_adapter,
    "real:accounts": accounts_adapter,
    "real:device_history": device_history_adapter,
    "real:login_history": login_history_adapter,
    "real:beneficiary": beneficiary_adapter,
    "real:fee_quote": fees_adapter,
    "real:my_loans": loans_adapter,
    "real:fd_profit_history": fd_profit_history_adapter,
    "real:dps_profit_history": dps_profit_history_adapter,
    "real:disputes": disputes_adapter,
    "real:cards": cards_adapter,
    # T-57: *** MUTATING exception *** -- see FreezeCardAdapter's own docstring.
    "real:frezz_unfrezz": freeze_card_adapter,
    # T-60: *** MUTATING exception *** -- see BeneficiaryAddAdapter's own docstring.
    "real:beneficiary_add": beneficiary_add_adapter,
    # T-64: read-only (GET) adapters.
    "real:my_tickets": complaints_adapter,
    "real:account_transactions": account_transactions_adapter,
    "real:card_limit_requests": card_limit_requests_adapter,
    "real:card_products": card_products_adapter,
    "real:virtual_card_requests": virtual_card_requests_adapter,
    "real:replacement_requests": replacement_requests_adapter,
    "real:credit_card_summary": credit_card_summary_adapter,
    "real:credit_card_statement": credit_card_statement_adapter,
    "real:profile": profile_adapter,
    "real:address": address_adapter,
    "real:contacts": contacts_adapter,
    "real:profile_change_requests": profile_change_requests_adapter,
    "real:contact_priority_requests": contact_priority_requests_adapter,
    "real:gifts_received": gifts_received_adapter,
    "real:email_transfers": email_transfers_adapter,
    "real:qr_payment_history": qr_payment_history_adapter,
    "real:transfer_limit": transfer_limit_adapter,
    "real:submit_complaint": SubmitComplaintAdapter(),
    "real:update_nickname": UpdateNicknameAdapter(),
    "real:update_address": UpdateAddressAdapter(),
    "real:update_email": UpdateEmailAdapter(),
    "real:update_mobile": UpdateMobileAdapter(),
}
