# User App API Map

`user_app` endpoint reference — what each screen calls, what comes back, and (for the two grids) how a response field turns into a route. Pulled from `user_app/lib`. As of 2026-09-01.

**Base URL:** `{bankingBaseUrl}` = `AppConfig.apiBaseUrl` (`.env` → `API_BASE_URL`). Client: `ApiClient` (`authorizedGet/Post/Put/Patch/Delete/Download`) — `lib/core/data/http/client/api_client.dart`. URLs centralized in `lib/core/data/http/urls/api_urls.dart`.

## Quick reference

| # | Feature | Method | Path | Nav mapper? |
|---|---|---|---|---|
| 1 | Services grid | GET | `support/v1/services` | Yes — local catalog |
| 2 | Pay & transfer | GET | `support/v1/pay-transfer` | Yes — local catalog + `action.type` |
| 3 | Transaction history | GET | `transfer/v1/accounting/transaction-list` | — |
| 4 | My account | GET | `polygon-bank/v1/accounts{/id}` | — |
| 5 | Balance | POST | `transfer/v1/accounting/balance` | — |
| 6 | Device history | GET | `auth/v1/devices` | — |
| 7 | Login history | GET | `auth/v1/devices/{id}/login-history` | — |

---

## 1. Services grid

`lib/features/services/`

**Endpoint:** `GET {bankingBaseUrl}support/v1/services`
Supports conditional GET — sends `If-None-Match`, handles 304. (`services_http_impl.dart:31–55`)

**Request:** none — GET, no body or query params.

**Response — `ServicesResponseDto` → `ServiceCategoryDto[]` → `ServiceItemDto[]`**

| Field | Type | Notes |
|---|---|---|
| `categories` | `ServiceCategoryDto[]` | from `data.categories` |
| `category.id` | `String` | |
| `category.name` | `String` | |
| `category.icon` | `String` | |
| `category.order` | `int` | json key `displayOrder` |
| `category.services` | `ServiceItemDto[]` | |
| `service.id` | `String` | **drives navigation** — see mapper below |
| `service.name` | `String` | |
| `service.isVisible` | `bool` | |
| `service.isActive` | `bool` | inactive → tap is a no-op |
| `service.order` | `int` | json key `displayOrder` |
| `service.icon` | `String?` | |

`lib/features/services/data/model/service_category_dto.dart:4,62` · `service_item_dto.dart:3`

**Navigation mapper**

The API sends only `service.id` (e.g. `transaction_history`) — never a route. Routing is joined locally against a static catalog.

1. On load, `ServicesController._attachRoutes()` maps every item's `id` through `LocalServiceCatalog.routeFor()` — a linear scan of static `{id, route}` pairs (e.g. `transaction_history`, `beneficiary`, `new_cheque_book`, `apply_for_loans`, `frezz_unfrezz`, `update_kyc`) — and stores the resolved route on the item.
2. On tap, `ServicesController.navigateToService()` checks `isActive` first — false means nothing happens.
3. If `route` resolved to `null` (id not in the local catalog), logs a warning and shows "This service is not available yet."
4. Otherwise `Get.toNamed(route)`.

`services_controller.dart:74–110` · `local_service_catalog.dart:10–72` · `local_service_definition.dart:9–14`

---

## 2. Pay & transfer

`lib/features/pay_transfer/`

**Endpoint:** `GET {bankingBaseUrl}support/v1/pay-transfer`
Same conditional-GET/etag pattern as services. (`pay_transfer_http_impl.dart:35–38`)

**Request:** none — GET, optional `If-None-Match`.

**Response — `PayTransferResponseDto` → `ServiceCategoryDto[]` → `ServiceItemDto[]` (recursive)**

| Field | Type | Notes |
|---|---|---|
| `categories` | `ServiceCategoryDto[]` | |
| `category.id` / `name` / `icon` | `String` | |
| `category.displayOrder` | `int` | |
| `category.isVisible` | `bool` | default true |
| `category.defaultExpanded` | `bool` | |
| `service.id` / `name` | `String` | |
| `service.isVisible` / `isActive` | `bool` | |
| `service.displayOrder` | `int` | |
| `service.isQuickOption` | `bool` | true → also shown in Home's Quick Actions grid |
| `service.icon` | `String?` | |
| `service.action` | `ServiceActionDto?` | |
| `action.type` | `String` | `"screen"` (default) or `"url"` |
| `action.target` | `String` | route id, or a URL when type is `url` |
| `service.subServices` | `ServiceItemDto[]` | recursive — same shape, drives sub-service sheet |

`lib/features/pay_transfer/data/model/service_category_dto.dart:4,74` · `service_item_dto.dart:3,27`

**Navigation mapper — `PayTransferServiceNavigator.open()`**

Checked in this order:

1. `isActive == false` → no-op.
2. Has `subServices` → opens `PayTransferSubServiceSheet` bottom sheet; picking a leaf recurses back into step 1 for that leaf.
3. `action.type == url` → `Get.toNamed(AppRoutes.webView, arguments: WebViewArgs(url: action.target, title: service.name))`.
4. Otherwise, uses the route resolved locally via `PayTransferLocalCatalog.routeFor(service.id)` (same `{id, route}` pattern as services grid). Null → warning log + "not available yet" snackbar. Resolved → `Get.toNamed(route, arguments: service.id)`.

`service_navigator.dart:16–60` · `local_service_catalog.dart` (pay_transfer)

> **Reused, not a separate endpoint** — Home's "Quick Actions" grid is *this same response*, filtered to `isQuickOption == true` and routed through the identical `PayTransferServiceNavigator.open()`. (`home_controller.dart:104–123`)

---

## 3. Transaction history

`lib/features/transaction_history/`

**Endpoint:** `GET {bankingBaseUrl}transfer/v1/accounting/transaction-list`

**Request — query params**

| Param | Type | Notes |
|---|---|---|
| `accountNumber` | `String` | required |
| `page` | `int` | required |
| `size` | `int` | required, controller default 10 |
| `isDownload` | `bool` | default false; true → PDF via `authorizedDownload` |
| `start` / `end` | `DateTime?` | optional filter, sent as MySQL date string |

`api_urls.dart:235–250` · `transaction_history_http_impl.dart:29–36,60–68`

**Response — `TransactionHistoryListResponse`** (flat shape, no `data` envelope)

| Field | Type | Notes |
|---|---|---|
| `openingBalance` | `String? → Money` | |
| `pagination.totalCount` | `int?` | |
| `pagination.currentPage` | `int?` | |
| `pagination.currentPageTotalCount` | `int?` | |
| `pagination.hasNext` | `bool?` | |
| `transactions[].id` | `dynamic` | |
| `transactions[].accountName` | `String?` | |
| `transactions[].accountNumber` | `String?` | |
| `transactions[].balance` | `Money?` | |
| `transactions[].fromToAccount` | `String?` | |
| `transactions[].type` | `String?` | `isCredit` = `type.toUpperCase() == 'CREDIT'` |
| `transactions[].amount` | `Money?` | |
| `transactions[].transactionType` | `String?` | |
| `transactions[].transactionId` | `String?` | |
| `transactions[].description` | `String?` | |
| `transactions[].txnTime` | `String? → DateTime` | |
| `transactions[].note` | `String?` | |
| `transactions[].isRefunded` | `bool?` | |
| `transactions[].isMerchant` | `bool?` | |

`transaction_history_list_response.dart:6,37,67`

---

## 4. My account

`lib/features/my_accounts/`

**Endpoints:**
- `GET {bankingBaseUrl}polygon-bank/v1/accounts`
- `GET {bankingBaseUrl}polygon-bank/v1/accounts/{id}`

Related: `.../by-number/{n}`, `.../{id}/transactions`, and starred toggles (`PUT .../{id}/quick-view` for accounts, `PUT card/v1/cards/{id}/quick-view` for cards). (`api_urls.dart:191–215`)

**Response — list unwraps to `accounts` + `ledgerAccounts`**

Envelope is `data` (else raw). Each account's stale `balance` is overridden with the live figure from `ledgerAccounts`, matched by `accountNumber`. Accounts may carry a nested `cards` array, parsed with different key names.

| Field | Type | Notes |
|---|---|---|
| `id` | `String?` | |
| `name` | `String?` | json key `accountName` |
| `number` | `String?` | json key `accountNumber` |
| `type` | `String?` | json key `accountType` — drives entity mapping (below) |
| `balance` | `Money` | |
| `isStarred` | `bool?` | json key `isStarred` or `starred` |
| `status` | `String?` | |
| `branchName, routingNumber, openingDate` | `String?` | |
| `accountId, linkedAccount, linkedAccountNumber, clientId` | `String?` | |
| `internationalTransactionStatus` | `String?` | |
| `maturityDate, tenureMonths` | `String?` | FD/DPS only |

`account_dto.dart:99,168,248` · `account_http_impl.dart:237–265`

**`type` → domain entity**

| `accountType` value | Maps to |
|---|---|
| `CURRENT` / `SAVINGS` | `BankAccount` |
| `DEBIT` / `CREDIT` / `PREPAID` / `VIRTUAL` | `CardAccount` |
| `LOAN` | `LoanAccount` |
| `FIXED_DEPOSIT` / `FDR` | `FixedDepositAccount` |
| `DPS` | `DpsAccount` |

`account_dto.dart:248–328` · `account.dart:95–383`

---

## 5. Balance

`lib/features/my_accounts/` — refresh-on-demand, not part of the account list payload.

**Endpoint:** `POST {bankingBaseUrl}transfer/v1/accounting/balance`

**Request body**

| Field | Type | Notes |
|---|---|---|
| `accountNumber` | `String` | a card/account number — for a card row, resolved to its *linked bank account* number via `Account.balanceAccountNumber` |

**Response**

No DTO class — envelope `data` (else raw) with a single `balance` field (String or num), parsed straight to `Money.fromPoisha(...)`. Return type of `GetAccountBalanceUseCase` is `Money`.

`account_http_impl.dart:70–88` · `get_account_balance_use_case.dart:5–13`

> **Callers** — `MyAccountsController.refreshBalance()` on balance-visibility toggle and on opening account detail. `HomeController.toggleBalance()` delegates to the same method. (`my_accounts_controller.dart:188–239` · `home_controller.dart:140–158`)

---

## 6. Device history

auth-service `UserDevice` / biometric devices. `lib/features/security/`

**Endpoints:**
- `GET {bankingBaseUrl}auth/v1/devices`
- `DELETE {bankingBaseUrl}auth/v1/devices/{deviceId}`
- `PATCH {bankingBaseUrl}auth/v1/devices/{deviceId}` — rename, body `{ "deviceName": String }`

**Response — `DeviceItemDto[]`** (`data` must be a List)

| Field | Type | Notes |
|---|---|---|
| `id` | `int` | |
| `deviceId` | `String` | |
| `deviceName` | `String?` | |
| `biometricEnabled` | `bool` | default false |
| `enrolledAt, lastUsedAt` | `DateTime` | |
| `fullName, username, profilePic` | `String?` | |
| `lastKnownIp` | `String?` | |
| `lastSeenCountry, lastSeenCity` | `String?` | |
| `lastSeenGeoLat/Lon` | `double?` | IP-derived |
| `lastSeenDeviceGeoLat/Lon` | `double?` | device GPS — preferred over IP-derived when present |
| `platform, os, browser` | `String?` | |
| `deviceCategory, appVersion, ipVersion` | `String?` | |

`device_item_dto.dart:3` · `device_item.dart:1–91` · `security_http_impl.dart:33–127`

---

## 7. Login history

auth-service `UserLoginAudit`. `lib/features/security/`

> **Not a standalone screen** — implemented as *per-device* history inside Device Management. No user-wide audit list exists in this app. If the spec expects a flat `/login-history` screen, it isn't built.

**Endpoint:** `GET {bankingBaseUrl}auth/v1/devices/{deviceId}/login-history`

**Request**

| Param | Type | Notes |
|---|---|---|
| `deviceId` | `String` | path |
| `page` | `int` | query, default 0 |
| `size` | `int` | query, default 20 |

**Response — `DeviceLoginRecordDto[]`** (`data.records`, or raw list fallback)

| Field | Type | Notes |
|---|---|---|
| `id` | `int` | |
| `status` | `String` | default FAILED; `isSuccess` checks `== 'SUCCESS'` |
| `loginType` | `String` | |
| `loginAt` | `DateTime` | |
| `ipAddress` | `String?` | |
| `failureReason` | `String?` | |
| `country, city` | `String?` | |
| `geoLat, geoLon` | `double?` | IP-derived |
| `deviceGeoLat, deviceGeoLon` | `double?` | device GPS — preferred when present |
| `newIp` | `bool` | default false |

`device_item_dto.dart:103` · `device_item.dart:93–132` · `device_management_controller.dart:59–95` (paginated, page size 20)

---

Both grids share the same local-catalog navigation pattern: `lib/core/presentation/navigation/local_service_definition.dart`.
