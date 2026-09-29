# Internet Banking API cURL Reference — 14 Chatbot Intents

Companion to [`Internet Banking API Intent Mapping.md`](Internet%20Banking%20API%20Intent%20Mapping.md).
Covers every endpoint listed under intents 1–14 of that mapping, and only those.

Generated 2026-09-29.

---

## How this document was verified

Every endpoint was checked against two sources, not guessed from its path:

1. **Backend controller + request DTO** in the monorepo (`<service>/src/main/java/...`). This gives the HTTP
   method, path/query parameters, required body fields (`@NotNull` / `@NotBlank`), and enum values.
2. **The Flutter app's actual call site** (`lib/core/data/http/urls/api_urls.dart` plus the feature `*_http_impl.dart`).
   This confirms how the client really calls the endpoint.

Each endpoint has one of these tags:

| Tag | Meaning |
|---|---|
| **CONFIRMED** | Method, parameters and body fields read directly from the backend controller/DTO. |
| **ASSUMPTION** | Some detail could not be read from code. The assumption is stated next to it. |
| **⚠️ NO BACKEND** | The app calls this URL, but **no controller in the monorepo serves it**. The cURL is built from the app's call site only. Expect `404` until the backend is built. |

"Source" lines give the controller file, shortened as `<service>/…/<File>.java`.

### Common conventions (CONFIRMED unless noted)

| Item | Value |
|---|---|
| Base URL | `https://internet-banking.dev-polygontech.xyz`, the dev environment, taken from `API_BASE_URL` in `user_app/.env`. For local Kong, swap in `http://localhost:10000`. |
| Auth | `Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc`. The token comes from `POST /auth/v1/auth/login`. The backend reads the user ID from the JWT, so **no endpoint below takes a `userId`**. |
| Public (no JWT) endpoints in this list | `support/v1/ai/public/chat` and `support/v1/ai/public/status` (Kong route `support-ai-public`, rate-limited to 10/min per IP). Kong also exposes `polygon-bank/v1/accounts/by-number` without its JWT plugin (GET only). |
| Extra headers the app sends (not required by any controller here) | `Accept: application/json`, `Accept-language: en\|bn`, `Version: <apiVersion>` |
| Custom headers required | **None.** No controller in scope reads an `Idempotency-Key`, `X-*` or `deviceId` header. The one idempotency key in scope, for credit-card payment, goes in the **body**. |
| Money in transfer/bill bodies | `amount` is a **`Long` in poisha** (1 BDT = 100 poisha), so `50000` = ৳500.00. The **exception** is `merchant/v1/qr/pay`, where `amount` is a `BigDecimal` in **taka**, sent as a string like `"500.00"`. |
| `verificationToken` | UUID returned by `POST /otp/v1/verify` after an OTP is sent with `POST /otp/v1/send`. Required by every money-moving call and every sensitive card/profile action. |
| `pin` | The user's 6-digit **transaction PIN**. |
| `transactionTypeId` | An **admin-configured app-settings ID string**, such as the one on each Pay & Transfer menu leaf. It is response/config-dependent, so it is always a placeholder here. |
| Date format | `transaction-list` `start`/`end` use `yyyy-MM-dd`, from the app's `toMysqlDateString()`. `month` params use `yyyy-MM` (`YearMonth.parse`). |

---

# 1. ACCOUNT_INFO

### 1.1 Get all accounts

**Purpose:** List every bank account belonging to the logged-in user.
**Method:** GET — **CONFIRMED**
**Endpoint:** `polygon-bank/v1/accounts`
**Path params:** none · **Query params:** none
**Headers:** `Authorization`
**Body:** none
**Source:** `polygon-bank/…/AccountController.java` `getAccounts()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/polygon-bank/v1/accounts' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 1.2 Get account detail

**Purpose:** Get a single account by its internal numeric ID.
**Method:** GET — **CONFIRMED**
**Endpoint:** `polygon-bank/v1/accounts/{id}`
**Path params:** `id` (Long, internal account ID from 1.1)
**Query params:** none · **Body:** none
**Source:** `polygon-bank/…/AccountController.java` `getAccountById()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/polygon-bank/v1/accounts/<ACCOUNT_ID>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 1.3 Get account by account/card number

**Purpose:** Resolve an account from an account number or card number.
**Method:** GET — **CONFIRMED**
**Endpoint:** `polygon-bank/v1/accounts/by-number/{number}`
**Path params:** `number` (String: account number or card number)
**Query params:** none · **Body:** none
**Auth note:** Kong registers this as a separate GET-only route (`polygon-bank-by-number`) **without** the JWT plugin. Sending the Bearer token is harmless and matches what the app does.
**Source:** `polygon-bank/…/AccountController.java` `getByNumber()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/polygon-bank/v1/accounts/by-number/<ACCOUNT_OR_CARD_NUMBER>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 1.4 Get accounts by username

**Purpose:** List accounts linked to a username.
**Method:** GET — **CONFIRMED**
**Endpoint:** `polygon-bank/v1/accounts/by-username/{username}`
**Path params:** `username` (String)
**Query params:** none · **Body:** none
**Source:** `polygon-bank/…/AccountController.java` `getByUsername()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/polygon-bank/v1/accounts/by-username/<USERNAME>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 1.5 Star account for quick view

**Purpose:** Star or unstar an account on the dashboard quick view.
**Method:** PUT — **CONFIRMED**
**Endpoint:** `polygon-bank/v1/accounts/{id}/quick-view`
**Path params:** `id` (Long, internal account ID)
**Query params:** none
**Headers:** `Authorization`, `Content-Type: application/json`
**Body (`QuickViewRequest`):** `isStarred` (Boolean, required)
**Source:** `polygon-bank/…/AccountController.java` `toggleQuickView()`

```bash
curl --location --request PUT 'https://internet-banking.dev-polygontech.xyz/polygon-bank/v1/accounts/<ACCOUNT_ID>/quick-view' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "isStarred": true
  }'
```

### 1.6 My loans

**Purpose:** List the logged-in user's loan accounts.
**Method:** GET — **CONFIRMED**
**Endpoint:** `loan/v1/loans`
**Path params:** none · **Query params:** none · **Body:** none
**Source:** `loan/…/LoanController.java` `listMine()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/loan/v1/loans' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 1.7 FD profit history

**Purpose:** Profit/interest history of one fixed deposit.
**Method:** GET — **CONFIRMED**
**Endpoint:** `product/v1/fixed-deposit/{id}/profit-history`
**Path params:** `id` → backend name `fdIdentifier` (String, the FD identifier, **not** a numeric DB ID)
**Query params:** none · **Body:** none
**Source:** `product/…/FixedDepositController.java` `profitHistory()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/product/v1/fixed-deposit/<FD_IDENTIFIER>/profit-history' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 1.8 DPS profit history

**Purpose:** Profit/interest history of one DPS.
**Method:** GET — **CONFIRMED**
**Endpoint:** `product/v1/dps/{id}/profit-history`
**Path params:** `id` → backend name `dpsIdentifier` (String)
**Query params:** none · **Body:** none
**Source:** `product/…/DpsController.java` `profitHistory()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/product/v1/dps/<DPS_IDENTIFIER>/profit-history' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

---

# 2. ATM_SUPPORT

> **PARTIAL INTENT.** There is **no ATM locator API**. `locator/` is still a zero-entity skeleton, and no route is
> registered for it in local Kong. This intent is covered only by **borrowing** two capabilities:
> cardless cash withdrawal (fund-transfer) and transaction disputes (service-request).

### 2.1 Cash by code (cardless ATM withdrawal)

**Purpose:** Generate a cash code that the recipient uses at an ATM without a card.
**Method:** POST — **CONFIRMED**
**Endpoint:** `transfer/v1/cash-by-code`
**Path params:** none · **Query params:** none
**Headers:** `Authorization`, `Content-Type: application/json`
**Body (`CashByCodeRequest`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `fromAccount` | String | ✅ | source account number |
| `recipientMobile` | String | ✅ | `^01[3-9]\d{8}$` |
| `cashCodeDeliveryMethod` | enum | ✅ | `SCREEN_DISPLAY` \| `MOBILE_NUMBER` \| `EMAIL_ADDRESS` |
| `deliveryEmail` | String | — | valid email; needed when method is `EMAIL_ADDRESS` (ASSUMPTION: enforced in the service, not the DTO) |
| `transactionTypeId` | String | ✅ | admin-configured |
| `amount` | Long (poisha) | ✅ | > 0 |
| `verificationToken` | String | ✅ | from OTP verify |
| `pin` | String | ✅ | transaction PIN |
| `referenceNo`, `note`, `categoryId` (Long), `customCategoryId` | — | — | optional |

**Source:** `fund-transfer/…/CashByCodeController.java`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/cash-by-code' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "fromAccount": "<ACCOUNT_NUMBER>",
    "recipientMobile": "01712345678",
    "cashCodeDeliveryMethod": "MOBILE_NUMBER",
    "transactionTypeId": "<TRANSACTION_TYPE_ID>",
    "amount": 200000,
    "note": "<NOTE>",
    "verificationToken": "<VERIFICATION_TOKEN>",
    "pin": "<TRANSACTION_PIN>"
  }'
```

### 2.2 Raise dispute (ATM debit problem)

**Purpose:** Dispute a transaction, for example when an ATM debited the account but dispensed no cash.
**Method:** POST — **CONFIRMED**
**Endpoint:** `service-request/v1/disputes`
**Headers:** `Authorization`, `Content-Type: application/json`
**Body (`RegisterDisputeRequest`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `accountNumber` | String | ✅ | |
| `transactionReferenceNo` | String | ✅ | from the transaction list |
| `category` | enum | ✅ | `UNAUTHORIZED_TRANSACTION` \| `DUPLICATE_CHARGE` \| `AMOUNT_MISMATCH` \| `SERVICE_NOT_RENDERED` \| `OTHER` |
| `remarks` | String | — | |
| `otpType` | enum | ✅ | `SMS` \| `EMAIL` |
| `verificationToken` | String | ✅ | |

There is no ATM-specific category. `SERVICE_NOT_RENDERED` (debited, no cash) is the closest fit, and that choice is an ASSUMPTION.
**Source:** `service-request/…/DisputeController.java` `submit()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/service-request/v1/disputes' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "accountNumber": "<ACCOUNT_NUMBER>",
    "transactionReferenceNo": "<TRANSACTION_REFERENCE_NO>",
    "category": "SERVICE_NOT_RENDERED",
    "remarks": "ATM debited account but no cash dispensed",
    "otpType": "SMS",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 2.3 List disputes

**Purpose:** List the disputes raised on an account, to follow up on an ATM dispute.
**Method:** GET — **CONFIRMED**
**Endpoint:** `service-request/v1/disputes`
**Query params:** `accountNumber` (String, **required**)
**Source:** `service-request/…/DisputeController.java` `getByAccountNumber()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/service-request/v1/disputes?accountNumber=<ACCOUNT_NUMBER>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

---

# 3. CARD_ISSUE

> **PARTIAL INTENT.** There is **no dedicated "card not working" / diagnostics API**. This intent borrows
> card lifecycle actions (reset PIN, unfreeze) from CARD_MANAGEMENT, disputes from service-request, and complaints
> from support.

### 3.1 Reset card PIN

**Purpose:** Reset the card PIN.
**Method:** PATCH — **CONFIRMED**
**Endpoint:** `card/v1/cards/{id}/reset-pin`
**Path params:** `id` (Long, card ID from the card list)
**Headers:** `Authorization`, `Content-Type: application/json`
**Body (`CardLifecycleActionRequest`):** `verificationToken` (✅), `pin` (optional), `password` (optional)
**ASSUMPTION:** `pin` and `password` are alternative re-authentication factors, so send one of them. The DTO marks neither as required. Which one is enforced is decided in the service layer.
**Source:** `card/…/CardLifecycleController.java` `resetPin()`

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/reset-pin' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 3.2 Unfreeze card

**Purpose:** Unfreeze a card that was frozen.
**Method:** PATCH — **CONFIRMED**
**Endpoint:** `card/v1/cards/{id}/unfreeze`
**Path params:** `id` (Long)
**Body (`CardLifecycleActionRequest`):** `verificationToken` (✅), `pin` / `password` (optional; same ASSUMPTION as 3.1)
**Source:** `card/…/CardLifecycleController.java` `unfreeze()`

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/unfreeze' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 3.3 Raise dispute

**Purpose:** Dispute a card transaction.
**Method:** POST — **CONFIRMED** (same contract as 2.2)
**Endpoint:** `service-request/v1/disputes`
**Source:** `service-request/…/DisputeController.java` `submit()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/service-request/v1/disputes' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "accountNumber": "<ACCOUNT_NUMBER>",
    "transactionReferenceNo": "<TRANSACTION_REFERENCE_NO>",
    "category": "UNAUTHORIZED_TRANSACTION",
    "remarks": "<REMARKS>",
    "otpType": "SMS",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 3.4 List disputes

**Method:** GET — **CONFIRMED** (same as 2.3)
**Endpoint:** `service-request/v1/disputes` · **Query:** `accountNumber` (required)

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/service-request/v1/disputes?accountNumber=<ACCOUNT_NUMBER>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 3.5 Submit complaint

**Purpose:** Log a complaint ticket about a card problem.
**Method:** POST — **CONFIRMED**
**Endpoint:** `support/v1/complaints`
**Headers:** `Authorization`, `Content-Type: application/json`
**Body (`SubmitComplaintRequest`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `category` | enum | ✅ | `ACCOUNT` \| `CARD` \| `TRANSACTION` \| `LOAN_DEPOSIT` \| `MOBILE_APP_TECHNICAL` \| `SERVICE_QUALITY` \| `OTHER` |
| `description` | String | ✅ | max 2000 chars |

**Source:** `support/…/ComplaintController.java` `submit()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/support/v1/complaints' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "category": "CARD",
    "description": "<DESCRIPTION>"
  }'
```

### 3.6 My complaints

**Purpose:** List the user's complaints.
**Method:** GET — **CONFIRMED**
**Endpoint:** `support/v1/complaints` · no params
**Source:** `support/…/ComplaintController.java` `listMine()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/support/v1/complaints' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

---

# 4. CARD_MANAGEMENT

All endpoints in this section are served by `card/`. "Card ID" means the numeric `id` from the card list.

### 4.1 Freeze card

**Purpose:** Temporarily freeze a card.
**Method:** PATCH — **CONFIRMED**
**Endpoint:** `card/v1/cards/{id}/freeze`
**Path params:** `id` (Long)
**Body (`FreezeCardRequest`):** `reasonCode` (✅, enum; the only value today is `OTHER`), `verificationToken` (✅), `pin` / `password` (optional; see the 3.1 ASSUMPTION)
**Source:** `card/…/CardLifecycleController.java` `freeze()`

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/freeze' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "reasonCode": "OTHER",
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 4.2 Unfreeze card

**Method:** PATCH — **CONFIRMED** (same contract as 3.2)

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/unfreeze' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 4.3 Close card

**Purpose:** Permanently close a card.
**Method:** PATCH — **CONFIRMED**
**Endpoint:** `card/v1/cards/{id}/close`
**Body (`CardLifecycleActionRequest`):** `verificationToken` (✅), `pin` / `password` (optional)
**Source:** `card/…/CardLifecycleController.java` `close()`

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/close' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 4.4 Contactless on/off

**Purpose:** Enable or disable contactless (tap) payments and optionally set a limit.
**Method:** PATCH — **CONFIRMED**
**Endpoint:** `card/v1/cards/{id}/contactless`
**Body (`ContactlessPreferenceRequest`):** `enabled` (Boolean, ✅), `limitPoisha` (Long, optional, in poisha)
**Note:** Unlike the other lifecycle calls, this one needs **no** `verificationToken` or PIN.
**Source:** `card/…/CardLifecycleController.java` `updateContactless()`

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/contactless' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "enabled": true,
    "limitPoisha": 500000
  }'
```

### 4.5 International transaction on/off

**Method:** PATCH — **CONFIRMED**
**Endpoint:** `card/v1/cards/{id}/international-transaction`
**Body (`InternationalTransactionPreferenceRequest`):** `enabled` (✅), `verificationToken` (✅), `pin` / `password` (optional)
**Source:** `card/…/CardLifecycleController.java` `updateInternationalTransaction()`

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/international-transaction' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "enabled": true,
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 4.6 Reset card PIN

**Method:** PATCH — **CONFIRMED** (same contract as 3.1)

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/reset-pin' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 4.7 Card limit change — submit request

**Purpose:** Ask for a new credit limit (maker-checker, reviewed by the bank).
**Method:** POST — **CONFIRMED** (returns `201 Created`)
**Endpoint:** `card/v1/cards/{id}/limit-change-requests`
**Path params:** `id` → backend name `cardId` (Long)
**Body (`SubmitCardLimitChangeRequest`):** `requestedCreditLimitPoisha` (BigDecimal, ✅, > 0, poisha), `reason` (optional)
**Source:** `card/…/CardLimitChangeController.java` `submit()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/limit-change-requests' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "requestedCreditLimitPoisha": 20000000,
    "reason": "<REASON>"
  }'
```

### 4.8 Card limit change — list my requests

**Method:** GET — **CONFIRMED**
**Endpoint:** `card/v1/cards/limit-change-requests`
**Query params:** `page` (int, default `0`), `size` (int, default `10`)
**Source:** `card/…/CardLimitChangeController.java` `listMine()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/limit-change-requests?page=0&size=10' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 4.9 Card limit change — cancel request

**Method:** DELETE — **CONFIRMED**
**Endpoint:** `card/v1/cards/limit-change-requests/{id}`
**Path params:** `id` (Long, the **request** ID from 4.8, not the card ID)
**Source:** `card/…/CardLimitChangeController.java` `cancel()`

```bash
curl --location --request DELETE 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/limit-change-requests/<REQUEST_ID>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 4.10 Card products list

**Purpose:** List the card products available to apply for.
**Method:** GET — **CONFIRMED**
**Endpoint:** `card/v1/card-products`
**Query params (all optional):** `cardCategory`, `scheme`, `domesticNetwork`, `internationalNetwork` (Strings; exact allowed values are not enumerated in the controller)
**Source:** `card/…/CardProductController.java` `listAvailable()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/card-products' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'

# filtered (values require confirmation)
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/card-products?cardCategory=<CARD_CATEGORY>&scheme=<SCHEME>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 4.11 Apply for debit card

**Method:** POST — **CONFIRMED** (`201 Created`)
**Endpoint:** `card/v1/cards/debit`
**Body (`DebitCardApplicationRequest`):**

| Field | Type | Required |
|---|---|---|
| `holderName` | String | ✅ |
| `linkedAccountNumber` | String | ✅ |
| `linkedAccountId` | Long | — |
| `cardProductId` | Long | ✅ (from 4.10) |
| `physical` | boolean | — (default `false`) |
| `verificationToken` | String | ✅ |
| `pin` / `password` | String | — (see 3.1 ASSUMPTION) |

**Source:** `card/…/DebitCardApplicationController.java` `apply()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/debit' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "holderName": "<HOLDER_NAME>",
    "linkedAccountNumber": "<ACCOUNT_NUMBER>",
    "cardProductId": <CARD_PRODUCT_ID>,
    "physical": true,
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 4.12 Reveal debit card details

**Method:** GET — **CONFIRMED**
**Endpoint:** `card/v1/cards/debit/{id}/reveal`
**Path params:** `id` → backend `cardId` (Long)
**Source:** `card/…/DebitCardApplicationController.java` `reveal()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/debit/<CARD_ID>/reveal' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 4.13 Apply for prepaid card

**Method:** POST — **CONFIRMED** (`201 Created`)
**Endpoint:** `card/v1/cards/prepaid`
**Body (`PrepaidCardApplicationRequest`):** the same fields as 4.11, plus these optional ones:
`maxBalancePoisha` (BigDecimal), `initialLoadAmountPoisha` (BigDecimal), `sourceAccountId` (Long).
**Warning:** per `CLAUDE.md`, prepaid applications fail unless `CARD_PREPAID_COA_ID` and `CARD_PREPAID_APP_SETTINGS_ID` are provisioned in accounting.
**Source:** `card/…/PrepaidCardApplicationController.java` `apply()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/prepaid' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "holderName": "<HOLDER_NAME>",
    "linkedAccountNumber": "<ACCOUNT_NUMBER>",
    "cardProductId": <CARD_PRODUCT_ID>,
    "maxBalancePoisha": 10000000,
    "initialLoadAmountPoisha": 100000,
    "sourceAccountId": <SOURCE_ACCOUNT_ID>,
    "physical": false,
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 4.14 Reveal prepaid card details

**Method:** GET — **CONFIRMED**
**Endpoint:** `card/v1/cards/prepaid/{id}/reveal`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/prepaid/<CARD_ID>/reveal' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 4.15 Virtual card — submit request

**Method:** POST — **CONFIRMED** (`201 Created`)
**Endpoint:** `card/v1/cards/virtual/requests`
**Body (`VirtualCardRequestCreateRequest`):** `linkedAccountNumber` (✅), `cardProductId` (Long, ✅), `holderName` (✅). No OTP or PIN is needed.
**Source:** `card/…/VirtualCardController.java` `submit()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/virtual/requests' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "linkedAccountNumber": "<ACCOUNT_NUMBER>",
    "cardProductId": <CARD_PRODUCT_ID>,
    "holderName": "<HOLDER_NAME>"
  }'
```

### 4.16 Virtual card — list my requests

**Method:** GET — **CONFIRMED**
**Endpoint:** `card/v1/cards/virtual/requests` · **Query:** `page` (default 0), `size` (default 10)

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/virtual/requests?page=0&size=10' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 4.17 Virtual card — cancel request

**Method:** DELETE — **CONFIRMED**
**Endpoint:** `card/v1/cards/virtual/requests/{id}` (`id` = request ID)

```bash
curl --location --request DELETE 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/virtual/requests/<REQUEST_ID>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 4.18 Virtual card — reveal details

**Method:** GET — **CONFIRMED**
**Endpoint:** `card/v1/cards/virtual/requests/{id}/reveal`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/virtual/requests/<REQUEST_ID>/reveal' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 4.19 Star card for quick view

**Method:** PUT — **CONFIRMED**
**Endpoint:** `card/v1/cards/{id}/quick-view`
**Query params:** `isStarred` (boolean, **required**)
**Body:** none. The flag is a **query param** here, unlike the account quick view (1.5), where it goes in the body. The app sends an empty `{}` body.
**Source:** `card/…/CardController.java` `toggleQuickView()`

```bash
curl --location --request PUT 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/quick-view?isStarred=true' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 4.20 Credit card bill payment (card service)

**Purpose:** Pay a credit card's outstanding balance from a source account.
**Method:** POST — **CONFIRMED**
**Endpoint:** `card/v1/cards/{id}/credit-card/payment`
**Body (`CreditCardPaymentRequest`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `paymentType` | String (enum) | ✅ | `TOTAL_OUTSTANDING` \| `STATEMENT_DUE` \| `MINIMUM_DUE` |
| `sourceAccountId` | String | ✅ | parsed with `Long.parseLong`, so it must be a **numeric** account ID sent as a string |
| `idempotencyKey` | String | ✅ | client-generated UUID; a repeat returns the original payment |

**Note:** the body has **no amount**. The amount comes from `paymentType`. No OTP or PIN is required by the DTO.
**Source:** `card/…/CardController.java` `payCreditCard()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/credit-card/payment' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "paymentType": "STATEMENT_DUE",
    "sourceAccountId": "<SOURCE_ACCOUNT_ID>",
    "idempotencyKey": "<UUID>"
  }'
```

### 4.21 Credit card bill payment (bill-payment service)

**Purpose:** Pay a card bill through the generic bill-payment pipeline.
**Method:** POST — **CONFIRMED**
**Endpoint:** `bill/v1/payment/card_payment`. The backend route is `POST /bill/v1/payment/{category}`, and here `category = card_payment`.
**Body (`PaymentRequest`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `fromAccount` | String | ✅ | |
| `billerReference` | String | — | ASSUMPTION: the card number being paid |
| `operator` | String | — | not used for card payment (mobile recharge only) |
| `connectionType` | enum | — | `PREPAID` \| `POSTPAID`, for mobile recharge only |
| `transactionTypeId` | String | ✅ | |
| `amount` | Long (poisha) | ✅ | |
| `verificationToken` | String | ✅ | |
| `pin` | String | ✅ | |
| `referenceNo`, `note`, `categoryId`, `customCategoryId` | — | — | optional |

**Source:** `bill-payment/…/PaymentController.java` `pay()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/bill/v1/payment/card_payment' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "fromAccount": "<ACCOUNT_NUMBER>",
    "billerReference": "<CARD_NUMBER>",
    "transactionTypeId": "<TRANSACTION_TYPE_ID>",
    "amount": 500000,
    "verificationToken": "<VERIFICATION_TOKEN>",
    "pin": "<TRANSACTION_PIN>"
  }'
```

### 4.22 QR payment cards — list  ⚠️ NO BACKEND

**Purpose:** List the user's cards with their "enabled for QR payment" flag.
**Method:** GET (from the app's `security_http_impl.dart` `getCards()`)
**Endpoint:** `auth/v1/user/qr-settings/cards`
**Status:** No controller in `auth/`, or anywhere else in the monorepo, maps `qr-settings`. The app falls back to local data (`_fallbackCardsOrFailure`) when the call fails.

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/auth/v1/user/qr-settings/cards' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 4.23 QR payment card — enable/disable  ⚠️ NO BACKEND

**Method:** PUT (from the app's `setCardEnabled()`)
**Endpoint:** `auth/v1/user/qr-settings/cards/{id}`
**Body (what the app sends):** `enabledForQr` (Boolean). The server contract is unconfirmed because the endpoint doesn't exist.

```bash
curl --location --request PUT 'https://internet-banking.dev-polygontech.xyz/auth/v1/user/qr-settings/cards/<CARD_ID>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "enabledForQr": true
  }'
```

---

# 5. CARD_REPLACEMENT

### 5.1 List replacement requests

**Method:** GET — **CONFIRMED**
**Endpoint:** `card/v1/cards/replacement-requests`
**Query params:** `page` (default 0), `size` (default 10)
**Source:** `card/…/CardReplacementController.java` `listMine()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/replacement-requests?page=0&size=10' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 5.2 Cancel replacement request

**Method:** DELETE — **CONFIRMED**
**Endpoint:** `card/v1/cards/replacement-requests/{id}` (`id` = replacement request ID)
**Source:** `card/…/CardReplacementController.java` `cancel()`

```bash
curl --location --request DELETE 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/replacement-requests/<REQUEST_ID>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 5.3 Reveal replacement card details

**Method:** GET — **CONFIRMED**
**Endpoint:** `card/v1/cards/replacement-requests/{id}/reveal`
**Source:** `card/…/CardReplacementController.java` `reveal()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/replacement-requests/<REQUEST_ID>/reveal' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

---

# 6. CHECK_BALANCE

### 6.1 Account balance

**Purpose:** Current ledger balance of an account.
**Method:** **POST** — **CONFIRMED**. The endpoint is a read, but the account number goes in a JSON body.
**Endpoint:** `transfer/v1/accounting/balance`
**Body (`BalanceRequest`):** `accountNumber` (String, ✅)
**Source:** `fund-transfer/…/AccountingController.java` `getBalance()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/accounting/balance' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "accountNumber": "<ACCOUNT_NUMBER>"
  }'
```

### 6.2 Credit card summary

**Purpose:** Credit limit, outstanding balance and available credit.
**Method:** GET — **CONFIRMED**
**Endpoint:** `card/v1/cards/{id}/credit-summary`
**Source:** `card/…/CardController.java` `getCreditSummary()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/credit-summary' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

---

# 7. EDIT_PERSONAL_DETAILS

### 7.1 Get profile

**Method:** GET — **CONFIRMED**
**Endpoint:** `auth/v1/user`
**Source:** `auth/…/UserManagementController.java` `getMyProfile()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/auth/v1/user' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 7.2 Update nickname

**Method:** PATCH — **CONFIRMED**
**Endpoint:** `auth/v1/user/profile/nickname`
**Body (`NickNameUpdateRequest`):** `nickName` (String, ✅). Note the capital **N**.
**Source:** `auth/…/UserManagementController.java` `updateMyNickName()`

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/auth/v1/user/profile/nickname' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "nickName": "<NICKNAME>"
  }'
```

### 7.3 Upload profile image (PATCH)

**Method:** PATCH — **CONFIRMED**
**Endpoint:** `auth/v1/user/profile/image`
**Content type:** `multipart/form-data` with the part named **`file`**
**Source:** `auth/…/UserManagementController.java` `uploadProfileImage()`

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/auth/v1/user/profile/image' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --form 'file=@"/path/to/profile.jpg"'
```

### 7.4 Upload profile image (POST variant)

**Method:** POST — **CONFIRMED**. The same path also accepts POST, but with a **different part name**.
**Content type:** `multipart/form-data` with the part named **`image`**
**Source:** `auth/…/UserManagementController.java` `uploadProfileImagePost()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/auth/v1/user/profile/image' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --form 'image=@"/path/to/profile.jpg"'
```

### 7.5 Update mobile number

**Method:** POST — **CONFIRMED**
**Endpoint:** `auth/v1/auth/mobile/update`
**Body (`UpdateMobileRequest`):** `newPhone` (✅, `^01[3-9]\d{8}$`), `verificationToken` (✅; ASSUMPTION: from an OTP sent to the **new** number)
**Source:** `auth/…/UserAuthController.java` `updateMobile()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/auth/v1/auth/mobile/update' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "newPhone": "01812345678",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 7.6 Update email address

**Method:** POST — **CONFIRMED**
**Endpoint:** `auth/v1/auth/email/update`
**Body (`UpdateEmailRequest`):** `newEmail` (✅, valid email), `verificationToken` (✅)
**Source:** `auth/…/UserAuthController.java` `updateEmail()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/auth/v1/auth/email/update' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "newEmail": "user@example.com",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 7.7 Get address (demographic profile)

**Method:** GET — **CONFIRMED**
**Endpoint:** `customer/v1/me/demographic`
**Source:** `customer/…/CustomerDemographicController.java` `getDemographic()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/customer/v1/me/demographic' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 7.8 Update address (demographic profile)

**Method:** PATCH — **CONFIRMED**
**Endpoint:** `customer/v1/me/demographic`
**Body (`UpdateDemographicRequest`, all optional, partial update):** `presentAddress`, `permanentAddress`, `district`, `division` (Strings), `preferredBankingMode` (`CONVENTIONAL` \| `ISLAMIC`)
**Source:** `customer/…/CustomerDemographicController.java` `updateDemographic()`

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/customer/v1/me/demographic' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "presentAddress": "<PRESENT_ADDRESS>",
    "permanentAddress": "<PERMANENT_ADDRESS>",
    "district": "<DISTRICT>",
    "division": "<DIVISION>"
  }'
```

### 7.9 Submit KYC

**Method:** POST — **CONFIRMED**
**Endpoint:** `customer/v1/me/kyc`
**Content type:** `multipart/form-data`
**Parts:**

| Part | Type | Required | Notes |
|---|---|---|---|
| `nidFront` | file | ✅ | |
| `nidBack` | file | ✅ | |
| `signature` | file | ✅ | |
| `occupation` | text | — | F-093 expected-transaction profile |
| `sourceOfFund` | text | — | |
| `monthlyIncome` | decimal, **poisha** | — | |
| `expectedMonthlyTurnover` | decimal, **poisha** | — | |

This list is complete (`CustomerDemographicController.java:72-82`).
**Source:** `customer/…/CustomerDemographicController.java` `submitKyc()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/customer/v1/me/kyc' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --form 'nidFront=@"/path/to/nid_front.jpg"' \
  --form 'nidBack=@"/path/to/nid_back.jpg"' \
  --form 'signature=@"/path/to/signature.png"' \
  --form 'occupation="<OCCUPATION>"' \
  --form 'sourceOfFund="<SOURCE_OF_FUND>"' \
  --form 'monthlyIncome="<POISHA>"' \
  --form 'expectedMonthlyTurnover="<POISHA>"'
```

### 7.10 My contacts

**Purpose:** List the customer's registered contacts (phones/emails). Its IDs feed 7.13.
**Method:** GET — **CONFIRMED**
**Endpoint:** `customer/v1/me/contacts`
**Source:** `customer/…/CustomerSelfController.java` `contacts()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/customer/v1/me/contacts' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 7.11 Profile change — submit request

**Purpose:** Request a change to a KYC-controlled field (maker-checker).
**Method:** POST — **CONFIRMED**
**Endpoint:** `service-request/v1/profile-changes`
**Body (`RegisterProfileChangeRequest`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `fieldName` | enum | ✅ | `MOBILE` \| `EMAIL` \| `NID` \| `LEGAL_NAME` \| `DOB` |
| `requestedValue` | String | ✅ | |
| `reason` | String | ✅ | |
| `otpType` | enum | ✅ | `SMS` \| `EMAIL` |
| `verificationToken` | String | ✅ | |

**Source:** `service-request/…/ProfileChangeController.java` `submit()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/service-request/v1/profile-changes' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "fieldName": "LEGAL_NAME",
    "requestedValue": "<NEW_VALUE>",
    "reason": "<REASON>",
    "otpType": "SMS",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 7.12 Profile change — list my requests

**Method:** GET — **CONFIRMED** · no params
**Source:** `service-request/…/ProfileChangeController.java` `getOwnRequests()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/service-request/v1/profile-changes' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 7.13 Contact priority — submit request

**Purpose:** Make one of the customer's contacts the primary one.
**Method:** POST — **CONFIRMED**
**Endpoint:** `service-request/v1/contact-priority`
**Body (`RegisterContactPriorityRequest`):** `contactId` (Long, ✅, from 7.10), `reason` (✅), `otpType` (✅, `SMS` \| `EMAIL`), `verificationToken` (✅)
**Source:** `service-request/…/ContactPriorityController.java` `submit()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/service-request/v1/contact-priority' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "contactId": <CONTACT_ID>,
    "reason": "<REASON>",
    "otpType": "SMS",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 7.14 Contact priority — list my requests

**Method:** GET — **CONFIRMED** · no params

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/service-request/v1/contact-priority' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

---

# 8. FAILED_TRANSFER

> **PARTIAL INTENT.** There is **no API to look up, re-check or retry one specific transfer** by ID. The bot has to
> **borrow** the transaction list (to find the transfer and read its status) from MINI_STATEMENT, plus disputes
> (service-request) and complaints (support).

### 8.1 Transaction history (read transfer status)

**Method:** GET — **CONFIRMED**
**Endpoint:** `transfer/v1/accounting/transaction-list`
**Query params:**

| Param | Type | Required | Default | Notes |
|---|---|---|---|---|
| `accountNumber` | String | ✅ | — | account or card number |
| `page` | int | — | `0` | |
| `size` | int | — | `10` | |
| `start` | String | — | — | `yyyy-MM-dd` |
| `end` | String | — | — | `yyyy-MM-dd` |
| `isDownload` | boolean | — | `false` | `true` returns a file (PDF) instead of JSON |

**Source:** `fund-transfer/…/AccountingController.java` `getTransactionListPdf()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/transfer/v1/accounting/transaction-list?accountNumber=<ACCOUNT_NUMBER>&page=0&size=10&isDownload=false&start=2026-09-01&end=2026-09-29' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 8.2 Raise dispute

**Method:** POST — **CONFIRMED** (contract in 2.2)

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/service-request/v1/disputes' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "accountNumber": "<ACCOUNT_NUMBER>",
    "transactionReferenceNo": "<TRANSACTION_REFERENCE_NO>",
    "category": "AMOUNT_MISMATCH",
    "remarks": "Transfer debited but not received by beneficiary",
    "otpType": "SMS",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 8.3 List disputes

**Method:** GET — **CONFIRMED** (`accountNumber` required)

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/service-request/v1/disputes?accountNumber=<ACCOUNT_NUMBER>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 8.4 Submit complaint

**Method:** POST — **CONFIRMED** (contract in 3.5)

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/support/v1/complaints' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "category": "TRANSACTION",
    "description": "<DESCRIPTION>"
  }'
```

### 8.5 My complaints

**Method:** GET — **CONFIRMED**

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/support/v1/complaints' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

---

# 9. FALLBACK

### 9.1 Polygon AI chat (logged in)

**Purpose:** RAG-backed AI assistant. It streams its answer as **Server-Sent Events**.
**Method:** POST — **CONFIRMED** (`produces = text/event-stream`)
**Endpoint:** `support/v1/ai/chat`
**Headers:** `Authorization`, `Content-Type: application/json`, `Accept: text/event-stream`. The controller reads `Authorization` itself (`required = false`), and Kong's JWT plugin still applies on `support-api`.
**Body (`AiChatRequest`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `message` | String | ✅ | max 2000 |
| `sessionKey` | String | — | reuse it to continue a conversation |
| `topK` | Integer | — | 1–20 |
| `category`, `service`, `subservice` | String | — | max 100 each |
| `payload` | object | — | free-form map |

**Source:** `support/…/AiChatController.java` `chat()`

```bash
curl --location --no-buffer --request POST 'https://internet-banking.dev-polygontech.xyz/support/v1/ai/chat' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --header 'Accept: text/event-stream' \
  --data '{
    "message": "How do I block my card?",
    "sessionKey": "<SESSION_KEY>"
  }'
```

### 9.2 Polygon AI chat (before login)

**Method:** POST — **CONFIRMED** (SSE)
**Endpoint:** `support/v1/ai/public/chat`
**Auth:** **none**. Kong route `support-ai-public` has no JWT and is rate-limited to 10 req/min per IP.
**Body:** `AiChatRequest` (same as 9.1)
**Source:** `support/…/PublicAiChatController.java` `chat()`

```bash
curl --location --no-buffer --request POST 'https://internet-banking.dev-polygontech.xyz/support/v1/ai/public/chat' \
  --header 'Content-Type: application/json' \
  --header 'Accept: text/event-stream' \
  --data '{
    "message": "What are your branch hours?"
  }'
```

### 9.3 Polygon AI status (logged in)

**Method:** GET — **CONFIRMED**
**Endpoint:** `support/v1/ai/status`
**Source:** `support/…/AiChatController.java` `status()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/support/v1/ai/status' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 9.4 Polygon AI status (public)

**Method:** GET — **CONFIRMED** · **no auth**
**Endpoint:** `support/v1/ai/public/status`
**Source:** `support/…/PublicAiChatController.java` `status()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/support/v1/ai/public/status'
```

### 9.5 FAQ categories

**Method:** GET — **CONFIRMED**
**Endpoint:** `support/v1/faq-categories` · no params
**Source:** `support/…/FaqController.java`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/support/v1/faq-categories' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 9.6 FAQs

**Method:** GET — **CONFIRMED**
**Endpoint:** `support/v1/faqs`
**Query params (optional):** `categoryId` (Long), `search` (String)
**Source:** `support/…/FaqController.java`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/support/v1/faqs?categoryId=<CATEGORY_ID>&search=<SEARCH_TEXT>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 9.7 Submit complaint

**Method:** POST — **CONFIRMED** (contract in 3.5)

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/support/v1/complaints' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "category": "OTHER",
    "description": "<DESCRIPTION>"
  }'
```

---

# 10. FEES

### 10.1 Transaction charge quote by type and amount

**Purpose:** Calculate the total fee/charge for a transaction type and amount before the user confirms.
**Method:** GET — **CONFIRMED**
**Endpoint:** `transfer/v1/transaction-type/charge-with-amount`
**Query params:**

| Param | Type | Required | Notes |
|---|---|---|---|
| `appSettingsId` | String | ✅ | the same admin-configured ID used as `transactionTypeId` in transfer bodies |
| `amount` | Long | ✅ | **poisha** (the app sends `amount.inPoisha`) |

**Source:** `fund-transfer/…/TransactionTypeController.java` `getTotalFeeByTransactionCode()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/transfer/v1/transaction-type/charge-with-amount?appSettingsId=<TRANSACTION_TYPE_ID>&amount=100000' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

---

# 11. GREETING

**No API / No cURL required.** The chatbot handles greetings directly in conversation.

---

# 12. LOST_OR_STOLEN_CARD

### 12.1 Report lost/stolen card

**Purpose:** Report a card lost or stolen and open a replacement request.
**Method:** POST — **CONFIRMED** (`201 Created`)
**Endpoint:** `card/v1/cards/{id}/replacement-requests`
**Path params:** `id` → backend `cardId` (Long)
**Body (`ReportLostStolenCardRequest`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `reasonCode` | enum | ✅ | `LOST` \| `STOLEN` \| `DAMAGED` \| `EXPIRED` \| `OTHER` |
| `verificationToken` | String | ✅ | |
| `pin` / `password` | String | — | see 3.1 ASSUMPTION |

**Source:** `card/…/CardReplacementController.java` `report()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/replacement-requests' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "reasonCode": "STOLEN",
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 12.2 Freeze card immediately

**Method:** PATCH — **CONFIRMED** (contract in 4.1)

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/freeze' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "reasonCode": "OTHER",
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

---

# 13. MINI_STATEMENT

### 13.1 Transaction list (paginated, date range)

**Method:** GET — **CONFIRMED** (full parameter table in 8.1)

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/transfer/v1/accounting/transaction-list?accountNumber=<ACCOUNT_NUMBER>&page=0&size=10&isDownload=false&start=<YYYY-MM-DD>&end=<YYYY-MM-DD>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 13.2 Account transactions

**Method:** GET — **CONFIRMED**
**Endpoint:** `polygon-bank/v1/accounts/{id}/transactions`
**Path params:** `id` (Long, internal account ID)
**Query params:** **none**. The controller takes no paging or date-range params.
**Source:** `polygon-bank/…/AccountController.java` `getTransactions()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/polygon-bank/v1/accounts/<ACCOUNT_ID>/transactions' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 13.3 Credit card statement (billed/unbilled)

**Method:** GET — **CONFIRMED**
**Endpoint:** `card/v1/cards/{id}/statements`
**Query params:** `isBilled` (boolean, **required**), `month` (String `yyyy-MM`, **required**)
**Source:** `card/…/CardController.java` `getStatement()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/card/v1/cards/<CARD_ID>/statements?isBilled=true&month=2026-09' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 13.4 Expense tracker — category transactions

**Method:** GET — **CONFIRMED**
**Endpoint:** `report/v1/expense-tracker/categories/{ref}/transactions`
**Path params:** `ref` → backend name `categoryId` (String; the app calls it `categoryRef`)
**Query params:** `month` (String, **required**; `yyyy-MM` is an ASSUMPTION based on the app and the rest of the expense tracker)
**Source:** `report/…/ExpenseTrackerController.java` `getCategoryTransactions()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/report/v1/expense-tracker/categories/<CATEGORY_REF>/transactions?month=2026-09' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

---

# 14. TRANSFER

All money-moving bodies below share these fields: `fromAccount` (✅), `transactionTypeId` (✅), `amount` (Long poisha, ✅, > 0),
`verificationToken` (✅), `pin` (✅), and the optional `referenceNo`, `note`, `categoryId` (Long), `customCategoryId`
(expense-tracker tagging).

### 14.1 Own account transfer

**Method:** POST — **CONFIRMED**
**Endpoint:** `transfer/v1/bank-transfer/own-account`
**Body (`OwnAccountTransferRequest`):** common fields + `toAccount` (✅)
**Source:** `fund-transfer/…/OwnAccountTransferController.java`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/bank-transfer/own-account' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "fromAccount": "<FROM_ACCOUNT_NUMBER>",
    "toAccount": "<TO_ACCOUNT_NUMBER>",
    "transactionTypeId": "<TRANSACTION_TYPE_ID>",
    "amount": 100000,
    "note": "<NOTE>",
    "verificationToken": "<VERIFICATION_TOKEN>",
    "pin": "<TRANSACTION_PIN>"
  }'
```

### 14.2 City Bank transfer

**Method:** POST — **CONFIRMED**
**Endpoint:** `transfer/v1/bank-transfer/city-bank`
**Body (`CityBankTransferRequest`):** common fields + `sendToType` (✅, `ACCOUNT` \| `MOBILE`) + `toAccount` (✅)
**Source:** `fund-transfer/…/CityBankTransferController.java`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/bank-transfer/city-bank' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "fromAccount": "<FROM_ACCOUNT_NUMBER>",
    "sendToType": "ACCOUNT",
    "toAccount": "<TO_ACCOUNT_NUMBER>",
    "transactionTypeId": "<TRANSACTION_TYPE_ID>",
    "amount": 100000,
    "verificationToken": "<VERIFICATION_TOKEN>",
    "pin": "<TRANSACTION_PIN>"
  }'
```

### 14.3 Other bank transfer

**Method:** POST — **CONFIRMED**
**Endpoint:** `transfer/v1/bank-transfer/other-bank`
**Body (`OtherBankTransferRequest`):** common fields plus:

| Field | Type | Required | Notes |
|---|---|---|---|
| `transferType` | enum | ✅ | `BEFTN` \| `NPSB` \| `RTGS` |
| `beneficiaryName` | String | ✅ | |
| `toAccount` | String | ✅ | |
| `bankName` | String | ✅ | |
| `district`, `branchName`, `routingNumber` | String | — | ASSUMPTION: routing is required by BEFTN/RTGS in practice; the DTO doesn't enforce it |

**Source:** `fund-transfer/…/OtherBankTransferController.java`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/bank-transfer/other-bank' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "fromAccount": "<FROM_ACCOUNT_NUMBER>",
    "transferType": "NPSB",
    "beneficiaryName": "<BENEFICIARY_NAME>",
    "toAccount": "<TO_ACCOUNT_NUMBER>",
    "bankName": "<BANK_NAME>",
    "district": "<DISTRICT>",
    "branchName": "<BRANCH_NAME>",
    "routingNumber": "<ROUTING_NUMBER>",
    "transactionTypeId": "<TRANSACTION_TYPE_ID>",
    "amount": 100000,
    "verificationToken": "<VERIFICATION_TOKEN>",
    "pin": "<TRANSACTION_PIN>"
  }'
```

### 14.4 Other banks list  ⚠️ NO BACKEND

**Method:** GET (from the app's `bank_transfer_http_impl.dart`)
**Endpoint:** `transfer/v1/other-banks`
**Status:** No controller in `fund-transfer/` (or anywhere else) maps `/transfer/v1/other-banks`. The request will 404 until it is built.

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/transfer/v1/other-banks' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.5 Gift transfer

**Method:** POST — **CONFIRMED**
**Endpoint:** `transfer/v1/bank-transfer/gift`
**Body (`GiftTransferRequest`):** common fields (**no `note`**) + `sendToType` (✅, `ACCOUNT` \| `MOBILE`), `toAccount` (✅), `giftTemplateId` (≤ 50 chars), `wishMessage` (≤ 500 chars)
**Source:** `fund-transfer/…/GiftTransferController.java` `transfer()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/bank-transfer/gift' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "fromAccount": "<FROM_ACCOUNT_NUMBER>",
    "sendToType": "MOBILE",
    "toAccount": "01712345678",
    "giftTemplateId": "<GIFT_TEMPLATE_ID>",
    "wishMessage": "Happy birthday!",
    "transactionTypeId": "<TRANSACTION_TYPE_ID>",
    "amount": 50000,
    "verificationToken": "<VERIFICATION_TOKEN>",
    "pin": "<TRANSACTION_PIN>"
  }'
```

### 14.6 Gifts received

**Method:** GET — **CONFIRMED**
**Endpoint:** `transfer/v1/bank-transfer/gift/received`
**Query params:** `page` (default 0), `size` (default 10; the app sends 20)
**Source:** `fund-transfer/…/GiftTransferController.java` `received()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/transfer/v1/bank-transfer/gift/received?page=0&size=20' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.7 Generic transaction

**Purpose:** Post a transaction of any configured type directly.
**Method:** POST — **CONFIRMED**
**Endpoint:** `transfer/v1/transactions/do-transaction`
**Body (`TransactionRequest`):**

| Field | Type | Required |
|---|---|---|
| `transactionTypeCode` | String | ✅ |
| `fromAccount` | String | ✅ |
| `toAccount` | String | ✅ |
| `amount` | Long (poisha) | ✅ |
| `referenceNo`, `note`, `transactionId`, `eventName`, `providedTrxnID` | String | — |

**Note:** unlike every other transfer here, this DTO has **no `verificationToken` or `pin`**. The controller wasn't
fully read for role restrictions, so confirm whether a USER token is allowed (**requires confirmation**).
**Source:** `fund-transfer/…/TransactionsController.java` `doTransaction()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/transactions/do-transaction' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "transactionTypeCode": "<TRANSACTION_TYPE_CODE>",
    "fromAccount": "<FROM_ACCOUNT_NUMBER>",
    "toAccount": "<TO_ACCOUNT_NUMBER>",
    "amount": 100000,
    "note": "<NOTE>"
  }'
```

### 14.8 Linked account check

**Method:** POST — **CONFIRMED**
**Endpoint:** `transfer/v1/accounting/linked-account`
**Body (`CheckLinkedAccountRequest`):** `accountNumber` (✅)
**Source:** `fund-transfer/…/BankTransferController.java` `checkLinkedAccount()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/accounting/linked-account' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "accountNumber": "<ACCOUNT_NUMBER>"
  }'
```

### 14.9 Email transfer — create

**Method:** POST — **CONFIRMED**
**Endpoint:** `transfer/v1/email-transfer`
**Body (`EmailTransferRequest`):** common fields + `recipientEmail` (✅, email), `securityQuestion` (✅), `securityAnswer` (✅)
**Source:** `fund-transfer/…/EmailTransferController.java` `transfer()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/email-transfer' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "fromAccount": "<FROM_ACCOUNT_NUMBER>",
    "recipientEmail": "recipient@example.com",
    "securityQuestion": "<SECURITY_QUESTION>",
    "securityAnswer": "<SECURITY_ANSWER>",
    "transactionTypeId": "<TRANSACTION_TYPE_ID>",
    "amount": 100000,
    "verificationToken": "<VERIFICATION_TOKEN>",
    "pin": "<TRANSACTION_PIN>"
  }'
```

### 14.10 Email transfer — list

**Method:** GET — **CONFIRMED**
**Endpoint:** `transfer/v1/email-transfer`
**Query params:** `tab` (String, default `pending`; other allowed values not enumerated in the controller, **requires confirmation**), `page` (default 0), `size` (default 10)

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/transfer/v1/email-transfer?tab=pending&page=0&size=10' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.11 Email transfer — details

**Method:** GET — **CONFIRMED**
**Endpoint:** `transfer/v1/email-transfer/{id}` (`id` Long)

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/transfer/v1/email-transfer/<EMAIL_TRANSFER_ID>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.12 Email transfer — cancel

**Method:** POST — **CONFIRMED**. It is POST, not DELETE.
**Endpoint:** `transfer/v1/email-transfer/{id}/cancel` · no body

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/email-transfer/<EMAIL_TRANSFER_ID>/cancel' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.13 Email transfer — resend notification

**Method:** POST — **CONFIRMED**
**Endpoint:** `transfer/v1/email-transfer/{id}/resend-notification` · no body

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/email-transfer/<EMAIL_TRANSFER_ID>/resend-notification' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.14 Wallet/MFS transfer

**Method:** POST — **CONFIRMED**
**Endpoint:** `transfer/v1/wallet-transfer`
**Body (`WalletTransferRequest`):** common fields + `walletNumber` (✅, `^01[3-9]\d{8}$`), `walletName` (optional), `walletTransferType` (optional, `DIRECT` \| `NPSB`)
**Source:** `fund-transfer/…/WalletTransferController.java` `transfer()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/transfer/v1/wallet-transfer' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "fromAccount": "<FROM_ACCOUNT_NUMBER>",
    "walletNumber": "01712345678",
    "walletName": "<WALLET_HOLDER_NAME>",
    "walletTransferType": "DIRECT",
    "transactionTypeId": "<TRANSACTION_TYPE_ID>",
    "amount": 100000,
    "verificationToken": "<VERIFICATION_TOKEN>",
    "pin": "<TRANSACTION_PIN>"
  }'
```

### 14.15 Wallet verify

**Method:** GET — **CONFIRMED**
**Endpoint:** `transfer/v1/wallet-transfer/verify`
**Query params:** `walletNumber` (String, **required**)
**Source:** `fund-transfer/…/WalletTransferController.java` `verify()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/transfer/v1/wallet-transfer/verify?walletNumber=01712345678' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.16 QR pay

**Method:** POST — **CONFIRMED**
**Endpoint:** `merchant/v1/qr/pay`
**Body (`QrPayRequest`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `referenceId` | String | ✅ | from the 14.17 parse response |
| `fromAccountId` | String | ✅ | |
| `amount` | BigDecimal | ✅ | **taka**, ≥ 0.01. The app sends a string such as `"500.00"`. This is the one exception to the poisha rule |
| `remarks` | String | — | |
| `pin` | String | ✅ | |
| `verificationToken` | String | ✅ | |

**Source:** `merchant/…/QrController.java` `payByQr()`

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/merchant/v1/qr/pay' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "referenceId": "<QR_REFERENCE_ID>",
    "fromAccountId": "<FROM_ACCOUNT_ID>",
    "amount": "500.00",
    "remarks": "<REMARKS>",
    "pin": "<TRANSACTION_PIN>",
    "verificationToken": "<VERIFICATION_TOKEN>"
  }'
```

### 14.17 QR parse

**Method:** POST — **CONFIRMED**
**Endpoint:** `merchant/v1/qr/parse`
**Body (`ParseQrRequest`):** `rawData` (String, ✅, the raw EMV/Bangla QR payload that was scanned)

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/merchant/v1/qr/parse' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "rawData": "<RAW_QR_STRING>"
  }'
```

### 14.18 QR payment history

**Method:** GET — **CONFIRMED**
**Endpoint:** `merchant/v1/qr/history` · **Query:** `page` (default 0), `size` (default 20)

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/merchant/v1/qr/history?page=0&size=20' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.19 Beneficiary — list

**Method:** GET — **CONFIRMED**
**Endpoint:** `beneficiary/v1/beneficiaries`
**Query params:** `serviceType` (optional enum: `OWN_BANK` \| `OTHER_BANK` \| `MFS` \| `CLUB_FEE` \| `DONATION` \| `EDUCATION_FEE` \| `INSURANCE` \| `UNIVERSAL_PENSION` \| `ZAKAT` \| `MOBILE_RECHARGE` \| `CARD_PAYMENT`)
**Source:** `beneficiary/…/BeneficiaryController.java` `list()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/beneficiary/v1/beneficiaries?serviceType=OTHER_BANK' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.20 Beneficiary — add

**Method:** POST — **CONFIRMED** (`201 Created`)
**Endpoint:** `beneficiary/v1/beneficiaries`
**Body (`CreateBeneficiaryRequest`):**

| Field | Type | Required | Notes |
|---|---|---|---|
| `serviceType` | enum | ✅ | see 14.19 |
| `nickname` | String | ✅ | |
| `identifierType` | enum | — | `CIF_NUMBER` \| `NID` \| `PASSPORT` \| `MOBILE` \| `EMAIL` \| `ACCOUNT_NUMBER` \| `CARD_NUMBER` \| `LOAN_ACCOUNT` |
| `accountNumber`, `accountHolderName` | String | — | |
| `bankName`, `branchName`, `district`, `routingNumber` | String | — | OTHER_BANK |
| `mfsProvider` | enum | — | MFS: `BKASH` \| `NAGAD` \| `ROCKET` \| `MYCASH` \| `SURECASH` \| `TELECASH` \| `OKWALLET` \| `UPAY` |
| `providerId` | String | — | biller-style types |

Which fields are required for each `serviceType` is checked in the service layer, not the DTO (**requires confirmation per type**).

```bash
curl --location --request POST 'https://internet-banking.dev-polygontech.xyz/beneficiary/v1/beneficiaries' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "serviceType": "OTHER_BANK",
    "nickname": "<NICKNAME>",
    "identifierType": "ACCOUNT_NUMBER",
    "accountNumber": "<ACCOUNT_NUMBER>",
    "accountHolderName": "<ACCOUNT_HOLDER_NAME>",
    "bankName": "<BANK_NAME>",
    "branchName": "<BRANCH_NAME>",
    "district": "<DISTRICT>",
    "routingNumber": "<ROUTING_NUMBER>"
  }'
```

### 14.21 Beneficiary — edit

**Method:** PATCH — **CONFIRMED**
**Endpoint:** `beneficiary/v1/beneficiaries/{id}` (`id` Long)
**Body (`UpdateBeneficiaryRequest`):** `nickname` (✅). **Only the nickname can be edited.**

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/beneficiary/v1/beneficiaries/<BENEFICIARY_ID>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "nickname": "<NEW_NICKNAME>"
  }'
```

### 14.22 Beneficiary — delete

**Method:** DELETE — **CONFIRMED** (a soft delete, per `CLAUDE.md`)
**Endpoint:** `beneficiary/v1/beneficiaries/{id}`

```bash
curl --location --request DELETE 'https://internet-banking.dev-polygontech.xyz/beneficiary/v1/beneficiaries/<BENEFICIARY_ID>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.23 Beneficiary — upload/change photo

**Method:** PATCH — **CONFIRMED** (`consumes = multipart/form-data`)
**Endpoint:** `beneficiary/v1/beneficiaries/{id}/photo`
**Part:** `file`

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/beneficiary/v1/beneficiaries/<BENEFICIARY_ID>/photo' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --form 'file=@"/path/to/photo.jpg"'
```

### 14.24 Beneficiary — remove photo

**Method:** DELETE — **CONFIRMED**
**Endpoint:** `beneficiary/v1/beneficiaries/{id}/photo`

```bash
curl --location --request DELETE 'https://internet-banking.dev-polygontech.xyz/beneficiary/v1/beneficiaries/<BENEFICIARY_ID>/photo' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.25 Beneficiary — pin/unpin

**Purpose:** Pin a beneficiary to the top of the list. "PIN" here means **pinning**, not a security PIN.
**Method:** PATCH — **CONFIRMED**
**Endpoint:** `beneficiary/v1/beneficiaries/{id}/pin`
**Body (`SetPinnedRequest`):** `pinned` (Boolean, ✅)

```bash
curl --location --request PATCH 'https://internet-banking.dev-polygontech.xyz/beneficiary/v1/beneficiaries/<BENEFICIARY_ID>/pin' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "pinned": true
  }'
```

### 14.26 Recipient lookup by account number

**Method:** GET — **CONFIRMED**. This is the same endpoint as 1.3. The mapping writes the param as `{id}`, but the backend names it `{number}`, and it is a String account/card number.
**Endpoint:** `polygon-bank/v1/accounts/by-number/{id}`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/polygon-bank/v1/accounts/by-number/<ACCOUNT_NUMBER>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.27 My transfer limit — get

**Method:** GET — **CONFIRMED**
**Endpoint:** `transfer/v1/my-limit/{account}` → backend name `accountIdentifier` (String)
**Source:** `fund-transfer/…/CustomerLimitController.java` `getMyLimit()`

```bash
curl --location 'https://internet-banking.dev-polygontech.xyz/transfer/v1/my-limit/<ACCOUNT_IDENTIFIER>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

### 14.28 My transfer limit — request change

**Method:** PUT — **CONFIRMED**. It uses the same path as 14.27; per rule 13 it is listed as a separate operation.
**Endpoint:** `transfer/v1/my-limit/{account}`
**Body (`ChangeLimitRequest`):** fields **not read** during verification (**requires confirmation**). Per `CLAUDE.md` (F-093), the request is risk-capped through a gRPC call to `customer-service`.

```bash
curl --location --request PUT 'https://internet-banking.dev-polygontech.xyz/transfer/v1/my-limit/<ACCOUNT_IDENTIFIER>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc' \
  --header 'Content-Type: application/json' \
  --data '{
    "<field>": "<value>"
  }'
```

### 14.29 My transfer limit — cancel pending change

**Method:** DELETE — **CONFIRMED**
**Endpoint:** `transfer/v1/my-limit/pending/{id}` (`id` Long, the pending request ID from the 14.27 response)
**Source:** `fund-transfer/…/CustomerLimitController.java` `cancelPendingChange()`

```bash
curl --location --request DELETE 'https://internet-banking.dev-polygontech.xyz/transfer/v1/my-limit/pending/<REQUEST_ID>' \
  --header 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJjaWYiOiIxMDkyNjAwMDAyMDIiLCJyb2xlIjoiVVNFUiIsInN0ZXBVcCI6ZmFsc2UsInJpc2siOiJOT1JNQUwiLCJ1c2VySWQiOjY2LCJzdWIiOiIwMTMxMTExMTExMCIsImp0aSI6IjkwYjNjMzgyLTFhYjAtNDdkOC05N2Q4LWI3YzVjNGEyODI2NCIsImlzcyI6ImludGVybmV0LWJhbmtpbmciLCJpYXQiOjE3OTA2NzkzMTMsImV4cCI6MTc5MDY4MDIxM30.2lAagoyWWvKXyAJIUcGdQak2EgPWB5JQJPRqjl2BBNc'
```

---

## API Coverage Summary

"Operation" means one cURL (one method + path). Shared endpoints are counted again under each intent that uses them.

| Intent | API/Operation Count | Method confirmed from backend code | Needs API docs / backend work to confirm | Notes |
|---|---:|---:|---:|---|
| ACCOUNT_INFO | 8 | 8 | 0 | |
| ATM_SUPPORT | 3 | 3 | 0 | **Partial.** No ATM locator. Borrows cash-by-code + disputes |
| CARD_ISSUE | 6 | 6 | 0 | **Partial.** Borrows card lifecycle, disputes, complaints |
| CARD_MANAGEMENT | 23 | 21 | 2 | The 2 `qr-settings/cards` ops have **no backend** |
| CARD_REPLACEMENT | 3 | 3 | 0 | |
| CHECK_BALANCE | 2 | 2 | 0 | Balance is **POST**, not GET |
| EDIT_PERSONAL_DETAILS | 14 | 14 | 0 | KYC and profile image are multipart |
| FAILED_TRANSFER | 5 | 5 | 0 | **Partial.** No single-transfer status/retry API |
| FALLBACK | 7 | 7 | 0 | Chat endpoints stream SSE |
| FEES | 1 | 1 | 0 | |
| GREETING | 0 | 0 | 0 | No API |
| LOST_OR_STOLEN_CARD | 2 | 2 | 0 | |
| MINI_STATEMENT | 4 | 4 | 0 | |
| TRANSFER | 29 | 28 | 1 | `other-banks` has **no backend**. `my-limit` PUT body unread |
| **Total** | **107** | **104** | **3** | |

---

## Confirmed vs Assumed — at a glance

**Confirmed from code (no documentation needed):**
- HTTP method, path variables, query params with defaults, and required body fields for 104 of 107 operations.
- Enum values: dispute category, complaint category, OTP type, freeze/replacement reason, credit payment type,
  transfer type, send-to type, wallet transfer type, beneficiary service/identifier type, MFS provider, banking mode, profile field.
- Multipart part names: `file` (profile image PATCH, beneficiary photo), `image` (profile image POST),
  `nidFront`/`nidBack`/`signature` (KYC).
- No custom headers are required by any controller in scope.
- Money units: poisha everywhere except `merchant/v1/qr/pay` (taka).

**Assumptions (marked inline as ASSUMPTION):**
- `pin` vs `password` on card lifecycle calls are treated as alternatives. The DTO requires neither.
- The `SERVICE_NOT_RENDERED` dispute category is used for ATM "debited, no cash".
- `deliveryEmail` is treated as required when `cashCodeDeliveryMethod = EMAIL_ADDRESS`.
- `billerReference` = card number for `bill/v1/payment/card_payment`.
- `routingNumber` is treated as practically required for BEFTN/RTGS.
- Expense tracker `month` format is `yyyy-MM`.

---

## Information Required From Backend/API Documentation

| # | Endpoint | What's missing | Why |
|---|---|---|---|
| 1 | `GET auth/v1/user/qr-settings/cards` | **Everything**: method, response, auth | No backend controller exists. The method comes only from the app. |
| 2 | `PUT auth/v1/user/qr-settings/cards/{id}` | **Everything**, including the body contract (`enabledForQr` is app-side only) | No backend controller exists. |
| 3 | `GET transfer/v1/other-banks` | **Everything**: response shape, pagination | No backend controller exists. |
| 4 | `PUT transfer/v1/my-limit/{account}` | Request body fields (`ChangeLimitRequest`) | DTO not read during this pass. |
| 5 | `POST transfer/v1/transactions/do-transaction` | Whether a customer (USER) token is allowed. Allowed `transactionTypeCode` values | No OTP/PIN in the DTO, which suggests it may be an internal/admin path. Role annotation not verified. |
| 6 | `POST customer/v1/me/kyc` | Accepted file types and max file size | Not declared on the controller. |
| 7 | Card lifecycle (`freeze`, `unfreeze`, `close`, `reset-pin`, `international-transaction`, `debit`, `prepaid`, `replacement-requests`) | Which of `pin` / `password` is actually enforced | Enforced in the service layer, not in the DTO. |
| 8 | `GET card/v1/card-products` | Allowed values for `cardCategory`, `scheme`, `domesticNetwork`, `internationalNetwork` | Plain `String` params, not enums. |
| 9 | `GET transfer/v1/email-transfer` | Allowed `tab` values other than `pending` | Plain `String` with a default. |
| 10 | `POST beneficiary/v1/beneficiaries` | Required fields for each `serviceType` | Validated in the service layer. |
| 11 | All transfer/bill bodies | Valid `transactionTypeId` / `appSettingsId` values | Admin-configured at runtime (accounting app-settings), not in code. |
| 12 | All endpoints | Response bodies/envelopes | Services differ: some return `ApiResponse<T>`, some `CommonResponse`, some raw DTOs/`Map`. Not documented here. |
| 13 | Response-dependent IDs | `<ACCOUNT_ID>` (1.1), `<CARD_ID>` (card list `GET card/v1/cards`, not itself in intents 1–14), `<REQUEST_ID>` (list endpoints), `<QR_REFERENCE_ID>` (14.17), `<CONTACT_ID>` (7.10), `<TRANSACTION_REFERENCE_NO>` (8.1), `<VERIFICATION_TOKEN>` (`POST /otp/v1/verify`) | Each must be taken from an earlier call's response. |
| 14 | `POST card/v1/cards/{id}/credit-card/payment` | Whether an OTP/PIN step is expected upstream | The DTO has none; only an idempotency key. |
