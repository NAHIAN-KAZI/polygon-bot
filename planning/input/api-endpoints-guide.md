# API Endpoints Guide (for AI/ML Engineers)

**Audience:** an AI/ML engineer who needs to understand the platform's API surface — e.g. to
wire an agent/RAG system into these services, build a tool-calling layer over them, or reason
about what the mobile app can and cannot do. This is not a general architecture doc — for that,
see the root `CLAUDE.md` and `docs/<service>.md`.

**Verified:** 2026-08-30, by reading the actual controller/security-config source and the
mobile app's networking code (not by trusting the root `CLAUDE.md` endpoint tables, which this
audit found to be stale in several places — noted inline below).

**Scope:** REST endpoints only. `accounting/` is gRPC-only (13 `@GrpcService` classes, ~87 RPCs,
no REST) and is the backbone every other service's ledger/limit/report calls depend on — see
`docs/` for that service if you need it. `deposit/`, `middleware/`, `locator/` are zero-entity
health-check skeletons, excluded.

---

## 1. How the platform is wired together

```
Mobile app (user_app, Flutter/GetX)  ─┐
Admin portals (Next.js)              ─┼─► Kong Gateway :10000 (JWT HS256, rate-limit 120/min) ─► one Spring Boot
3rd parties                          ─┘                                                          service per domain
                                                                                                        │
                                                                                        gRPC (cluster-only) ─► accounting/, customer/, beneficiary/, loan/
```

- Every service exposes `GET /<service>/v1/health` unauthenticated, and `/<service>/v1/internal/**`
  for cluster-only calls from other services (never routed through Kong to external clients).
- JWT is HS256, validated per-service. Most services keep a hand-maintained `permitAll()` list in
  `SecurityConfig`. **`auth/` is the one exception**: its `SecurityConfig` derives its public-path
  list directly from `JwtAuthenticationFilter.PUBLIC_PATHS`, so the filter and the security chain
  cannot drift from each other by construction — every other service's list is a literal string
  list maintained by hand, and can (and has) drifted from what the controllers actually enforce.
- **Response wrapper — correct this against `CLAUDE.md`:** there is no shared `ApiResponse<T>`
  class anywhere in the repo (`grep -rln "class ApiResponse"` — zero hits, including in
  `common-lib/`). All 19 services define their own local `CommonResponse` (essentially
  `{ message }`, used for ack/confirmation responses). Most endpoints don't wrap their response at
  all — they return the DTO or `List<DTO>` directly and let Spring serialize it. `customer/` uses
  a third, undocumented shape: ad-hoc `Map<String,Object>` via a `success(data)` helper. If you're
  writing a client or a schema for tool-calling, **do not assume a `{status,message,data,traceId}`
  envelope** — check the actual controller return type per endpoint.
- Two known security-config bugs (real bugs, not just doc drift, found during this audit):
  - `merchant/`: `SecurityConfig` marks `GET /merchant/v1/partners` as `permitAll()`, but the
    controller method still carries `@PreAuthorize("hasRole('ADMIN')")` — so it's not actually
    reachable without an admin JWT despite being "public."
  - `bill-payment/`: `/bill/v1/settings` is `permitAll()` for **all** methods including the
    mutating `POST`/`PATCH`, not just `GET` — anyone unauthenticated can write bill app settings.
- `CLAUDE.md`'s documented `POST /auth/v1/auth/login/pin` (API 6) **does not exist** in the
  current code. PIN/biometric login now lives at `POST /auth/v1/auth/biometric/login`. Stale
  dead entries for the old path remain in `JwtAuthenticationFilter.PUBLIC_PATHS`.
- Kong: `support-ai-public` route (`/support/v1/ai/public`, no JWT, rate-limited 10 req/min **by
  IP**) exists in `infra/local/kong/init.sh` but is missing from `CLAUDE.md`'s Kong table. The
  documented `support-public-app-icon` path is stale — actual path is
  `/support/v1/app-icon/active`, not `/support/v1/app-icon`. There's also a global
  `request-transformer` Kong plugin stripping inbound `X-Forwarded-For`/`X-Real-IP` — relevant if
  you're reasoning about IP-based logic (OTP throttling, login-audit IP capture) and not
  documented in `CLAUDE.md` at all.

---

## 2. Full backend endpoint inventory, by service

Legend: 🔓 public (no JWT) · 👤 authenticated user · 🛡 admin-only (`hasRole('ADMIN')`) ·
internal = cluster-only, never exposed via Kong to external clients.

### auth/ — port 8001, Kong `/auth`

Response type: `CommonResponse` (auth's own package). 35-endpoint `UserAuthController` is the
core: `/auth/v1/auth/{login, login/otp, logout, refresh-token, revoke-token, session,
change-password, forgot-password, reset-password, pin/*, identity/verify-*, login-settings/status,
settings/*, validate-session, email/*, security-questions*, login-history, security-alerts*}`.
Plus `TransactionPinController` (`/auth/v1/auth/tpin/*`), `UserBiometricController`
(`/auth/v1/auth/biometric/*`), `UserDeviceController` (`/auth/v1/devices/*`),
`UserManagementController` (profile + admin user management + `/auth/v1/internal/*`),
`AdminAuthController`/`AdminManagementController` (admin login/CRUD), `RoleController`
(`/auth/v1/role`), `SecurityEventController` (`GET /auth/v1/admin/security-events` 🛡).

### otp/ — port 8006, Kong `/otp`

Fully public (`permitAll()`, by design — called pre-login). `POST /otp/v1/{send,verify,resend,
validate-token}`.

### customer/ — port 8021, Kong `/customer` (CIF)

Three response conventions in one service: `CommonResponse` (5 uses), ad-hoc
`Map<String,Object>` via a `success()` helper (most controllers), and nothing shared. Admin CRUD
under `/customer/v1/admin/customers/*` (profile, addresses, contacts, KYC, relationships), risk
review queue `/customer/v1/admin/kyc-reviews/*` (F-093 maker-checker), self-service
`/customer/v1/me/*` (demographic, contacts, relationships, kyc-status, KYC submission — multipart
NID+signature+expected-transaction-profile), `/customer/v1/internal/*` for cluster callers.

### fund-transfer/ — port 8004, Kong `/transfer` — largest service, ~19 controllers

`AccountingController` (account CRUD, balance, transaction lists, limits — 🛡 heavy),
`TransactionsController` (do-transaction, refund, reverse), transfer-type controllers
(`own-account`, `other-bank`, `city-bank`, `wallet-transfer`, `email-transfer`, `cash-by-code`,
`add-money`), `CustomerLimitController` (self-service limit increase, F-093 risk-capped),
`ApprovalRequestController` (maker-checker queue), `ChartOfAccountController`,
`TransactionTypeController`/`TransactionLegController`, `MobileOperatorController`/
`RechargePackageController`.

### loan/ — port 8008, Kong `/loan`

`LoanController` (`/loan/v1/loans/*` — list, detail, emi-schedule, pay-emi, closure quote/execute,
stateless emi calculator), `AdminLoanController` (read-only), `LoanInternalController`
(`/loan/v1/internal/*` — `originate` and `certificate-data`, called by `service-request/`).

### card/ — port 8007, Kong `/card` — 20 controllers

Card CRUD/lifecycle (freeze/unfreeze/close/renew/contactless/reset-pin/international-toggle),
credit card (summary, payment, statements, applications), debit/prepaid/virtual card issuance +
reveal, replacement requests, limit-change requests, tokenization, preferences, card products,
reference data — most maker-checker flows have a customer controller + paired `*AdminController`.

### beneficiary/ — port 8011, Kong `/beneficiary`

`BeneficiaryController`: `GET/POST /beneficiary/v1/beneficiaries`, `PATCH/DELETE .../{id}` (soft
delete). Create/update gated by a manual `StepUpGuard.require(...)` call in the method body (not
an annotation) — real step-up MFA check, not just role-based.

### service-request/ — port 8012, Kong `/service-request`

8 request types, each with a customer controller (👤, POST create / GET list) + paired
`*AdminController` (🛡, GET admin list / PATCH approve / PATCH reject): deposit-closures,
cheque-books, cheque-stop, positive-pay, certificates, profile-changes, disputes, loan-requests.
Shared closure audit trail: `GET /service-request/v1/admin/audit/{requestType}/{requestId}` 🛡.

### merchant/ — port 8013, Kong `/merchant`

`QrController` (`/merchant/v1/qr/*` — parse, by-id, static, dynamic, pay, history — `pay` executes
via the shared Kafka money-movement pipeline), `PartnerController`, `MerchantAppSettingController`
(see the permitAll/`@PreAuthorize` bug noted in §1).

### report/ — port 8015, Kong `/report`

`ExpenseTrackerController` (`/report/v1/expense-tracker/*` — summary, trend, category
transactions, recategorize, exclude), `CategoryController` (categories + rules CRUD),
`AdminDashboardController` (`GET /report/v1/admin/dashboard/transaction-performance`, proxies
accounting's `GetTransactionReport` RPC), `MisExportController`, `UserActivityReportController`.

### campaign/ — port 8016, Kong `/campaign`

`CampaignController` (list + admin CRUD), `RewardsController` (`/campaign/v1/rewards/{summary,
points-history,vouchers}` + admin points/voucher recording).

### product/ — port 8020, Kong `/product` (FDR/DPS/remittance)

`FixedDepositController`/`DpsController` (open, list), `*InternalController` (closure-preview,
close — called by `service-request/`'s deposit-closure flow), `ProductController` (product
catalogue), `RemittanceController` (exchange houses, receive, history), admin exchange-house CRUD.

### support/ — port 8019, Kong `/support`

Broadest public surface of any service: `services`, `pay-transfer`, `bill-payment/categories`,
`merchant/partners`, `app-icon/active`, `ai/public/**` are all `permitAll()`. Also hosts
**Polygon AI** (`AiChatController`/`PublicAiChatController` — SSE-streaming RAG chat, the upstream
`X-API-Key` never leaves the cluster), complaints, FAQ, exchange rates, and a large admin-config
surface (app icons, menu categories, pay-transfer menu tree, app-service grid).

### polygon-bank/ — port 8003, Kong `/polygon-bank`

`AccountController` (CRUD, by-number/by-username lookup — both public, quick-view, transactions),
`InternalAccountController` (cluster-only — create, deduct, identity verify), plus 8 near-identical
sub-resource CRUD controllers (addresses, business, documents, eKYC, FATCA, occupations, PEP,
preferences) all under `/polygon-bank/v1/accounts/*`.

### bill-payment/ — port 8005, Kong `/bill`

`PaymentController` (`POST /bill/v1/payment/{category}` — one generic endpoint parameterized by
category: mobile_recharge, card_payment, club_fee, donation, universal_pension, insurance,
education, zakat), `PaymentCategoryController`, `BillerSubscriberController` (verify subscriber
before paying), `BillAppSettingController` (see permitAll bug in §1).

### notification/ — port 8010, Kong `/notification`

`NotificationController` (`/notification/v1/{notifications,preferences,device-token,
topics/{topic}/subscribe,unsubscribe}`), `NotificationProviderConfigController` (admin).

---

## 3. Endpoints the mobile app (`user_app/`) actually calls

The mobile app is Flutter + GetX (per root `CLAUDE.md` — **not** React Native; `mobile-app/`
described in the tech-stack table doesn't exist yet). It calls a subset of the full backend
surface above — mostly customer-facing, never admin (`/admin/*`) or internal (`/internal/*`)
paths. Full deduplicated list, verified by reading every `ApiUrl` definition and call site
(170 distinct endpoint calls, one confirmed dead/unwired stub excluded):

| Service | Representative endpoints called by `user_app` |
|---|---|
| `auth/` | login, biometric enroll/challenge/login, device bind/list/remove, PIN setup/reset, TPIN reset flow, identity verify (card/account), OTP-lock settings, login-history, profile update, refresh-token, logout, QR settings |
| `polygon-bank/` | registration (username check/set, verify-contact), accounts list/detail/by-number/by-username, transactions, quick-view toggle |
| `otp/` | send, verify |
| `card/` | quick-view, credit summary/payment/statements, freeze/unfreeze/close/contactless/reset-pin/international-toggle, virtual card issue/reveal, debit/prepaid card issue/reveal, replacement requests, limit-change requests, card products |
| `loan/` | list, emi-schedule, emi calculate, closure quote/execute, pay-emi |
| `transfer/` (fund-transfer) | balance, transaction-list, own-account/other-bank/city-bank/wallet transfer, email-transfer (+cancel/resend/claim), cash-by-code, linked-account lookup, my-limit, charge-with-amount, mobile-operators/recharge-packages |
| `bill/` (bill-payment) | payment by category (mobile recharge, card, club fee, donation, pension, insurance, education, zakat), biller-subscriber verify |
| `merchant/` | qr parse/by-id/static/dynamic/pay/history |
| `beneficiary/` | list, create, update, delete |
| `service-request/` | disputes, certificates (+document download), profile-changes, cheque-books, cheque-stop, positive-pay, deposit-closures, loan-requests (all create+list) |
| `support/` | services grid, pay-transfer menu, app-icon, exchange-rates, complaints, FAQ, AI chat (SSE, authenticated + public) |
| `customer/` | demographic get/patch, KYC submit |
| `product/` | products by type, fixed-deposit/DPS open, remittance exchange-houses/receive |
| `report/` | expense-tracker summary/trend/categories/recategorize/exclude |
| `notification/` | list, device-token register/remove, topic subscribe/unsubscribe |
| `campaign/` | campaigns list, rewards summary/points-history/vouchers |

Confirmed **not** called anywhere in `user_app`: any `/admin/*` path, any `/internal/*` path, and
`notification/v1/preferences` (a known gap — the preferences screen isn't built yet, matches a
note already in root `CLAUDE.md`).

---

## 4. How the mobile app calls an endpoint

**Stack:** `dio` (not `http`) wrapped in a single `ApiClient`
(`user_app/lib/core/data/http/client/api_client.dart`). No Retrofit-style annotations, no
OpenAPI codegen — endpoint URLs are hand-declared Dart strings.

**Base URL / environment:** `AppConfig` reads `API_BASE_URL` from `.env` via `flutter_dotenv`.
Current `user_app/.env` value: `https://internet-banking.dev-polygontech.xyz/` — note this is a
hosted dev gateway, **not** `http://localhost:10000` (the documented local Kong port). If you're
pointing a local backend stack at the mobile app for testing, you need to edit `.env`, not assume
Kong's local port is already wired in. There's no separate dev/staging/prod flavor split — one
`.env`, manually swapped; a pending TODO in `user_app/CLAUDE.md` notes it should move to
`--dart-define-from-file` instead of being bundled as an asset.

**Every endpoint path lives in one file:** `user_app/lib/core/data/http/urls/api_urls.dart`
(783 lines). ~35 `part` files declare abstract per-feature interfaces (no strings); the single
`ApiUrl` class in `api_urls.dart` is the sole implementer and holds every literal endpoint
string. No feature file hardcodes a raw URL outside this file.

**Auth:** `authorizedGet/Post/Patch/Put/Delete` methods attach `Authorization: Bearer <token>`;
plain `get/post/patch/delete` are for pre-login/public calls. On a 401 from an authorized call,
the client transparently calls `POST auth/v1/auth/refresh-token`, replays the original request,
and de-dupes concurrent refreshes so only one refresh call fires even if several requests 401 at
once. A failed refresh clears the token and routes the user to a session-timeout screen → login.

**Headers sent on every request:** `Accept`, `Accept-language`, `Version`, `deviceId`,
`deviceName`, `platform` (`IOS`/`ANDROID`), and — since the fraud/risk work — `geoLat`/`geoLon`
from the device's last known position, consumed by the backend's device/login risk scoring.

**Request flow (concrete example — own-account transfer):**

```
OwnAccountController (GetX controller, presentation layer)
  → TransferOwnAccountUseCase (domain/usecase — thin pass-through)
    → BankTransferHttpImpl.transferOwnAccount (data/repo_impl)
      → client.authorizedPost(_urls.ownAccountTransferUrl, body)
        → POST transfer/v1/bank-transfer/own-account
      ← BankTransferResultDto.fromJson(response).toEntity()
    ← Either<Failure, BankTransferResult>
  ← controller renders TransactionSuccessScreen
```

Every feature follows this same 5-layer shape: GetX controller → use case → repository
(`*HttpImpl` makes the Dio call and returns `Either<Failure, T>`, optionally wrapped by a
`*CacheImpl` that persists successful results to local prefs) → DTO (`fromJson`/`toEntity()`) →
entity. Repositories never touch `Dio` directly — only `ApiClient`. DI wiring (which
impl/use case/controller get bound together) happens in a per-feature `*Binding` class via
`Get.lazyPut(..., fenix: true)`.

**Non-standard call shapes worth knowing about:**
- SSE streaming (`authorizedPostSse`/`postSse`) bypasses the normal buffered response path
  entirely — used only by Polygon AI chat, returns a raw `Stream<String>` of SSE lines, with a
  240s receive timeout (vs. the 30s default — a real RAG response was observed taking 81s).
- Binary download (`authorizedDownload`) — separate path for PDFs, skips JSON error parsing.
- File uploads auto-convert `File`/`List<File>` map values into multipart form data.

---

## 5. How to add a new endpoint

### Backend (Spring Boot service)

1. Add a method to the feature's service **interface**, then implement it in the `*Impl` —
   constructor-inject the JPA repository plus any Kafka producer / gRPC client needed;
   `@Transactional` on mutating methods; soft-delete only (`deletedAt`), never hard-delete
   financial rows.
2. Add the controller method. Copy the `@PreAuthorize` expression from a sibling method in the
   *same* controller rather than inventing a new role expression.
3. **Two competing DTO-location conventions exist — match whichever the surrounding module
   already uses, don't introduce a third:**
   - Flat (older modules — `auth/`, `otp/`, most of `customer/`):
     `application/requests/`, `application/responses/`
   - DTO-subfolder (everything built since roughly mid-2026 — `beneficiary/`, `loan/`,
     `service-request/`, most of `card/`): `application/dto/request/`, `application/dto/response/`
4. Return type: usually the DTO/`List<DTO>` directly, or `CommonResponse` for ack-only
   responses. Don't invent a wrapper — there is no shared `ApiResponse<T>` (see §1).
5. If the endpoint must be public, add its exact path to that service's `SecurityConfig`
   `permitAll()` list — except in `auth/`, where you instead add it to
   `JwtAuthenticationFilter.PUBLIC_PATHS` (the security chain reads from there automatically).
6. Kong: most services already have a blanket prefix route (`/xxx` → `xxx-service:PORT`,
   `strip_path=false`), so a new path under an existing prefix needs no new Kong route. Only add
   one in `infra/local/kong/init.sh` if the new path needs *different* JWT/rate-limit behavior
   than the rest of the service (e.g. a new public sub-path on an otherwise-JWT-gated service).
7. Column naming: check the service's Hibernate physical-naming-strategy in `application.yaml`
   before writing a migration for a new camelCase field — see root `CLAUDE.md`'s column-naming
   table. When in doubt, use an explicit `@Column(name = "...")`.

### Mobile (`user_app`, Flutter/GetX)

1. Scaffold: `dart generate_feature.dart <snake_case_name>` from `user_app/` root — generates the
   10-file feature skeleton (entity, repo interface, use case, DTO, `*_http_impl.dart` with a
   `TODO` placeholder call, `*_cache_impl.dart`, controller, screen, binding, `pages.dart`).
2. Declare the endpoint path in `lib/core/data/http/urls/api_urls.dart`: add it to the relevant
   feature's abstract `XxxApiUrls` interface (or a new `part` file), then implement it as an
   `@override` getter/method on the single `ApiUrl` class, using `bankingBaseUrl` (not the dead
   `baseUrl` getter, which appends an unused `api/` segment):
   ```dart
   @override
   String get myNewThingUrl => '${bankingBaseUrl}my-service/v1/my-thing';
   ```
3. In the generated `*_http_impl.dart`, replace the `TODO` with the real call —
   `client.authorizedGet(...)` (or post/patch/put/delete), or plain `client.get(...)` for a
   pre-login endpoint — then parse the response via a DTO's `fromJson`/`toEntity()` and return
   `Either<Failure, T>`.
4. Fill in the DTO and entity fields to match the real response shape.
5. Register the route in `lib/res/routes/app_routes.dart` + `app_pages.dart`, and wire DI in the
   feature's `*Binding` (`Get.lazyPut<...>(..., fenix: true)` for
   `HttpImpl → Repository(CacheImpl) → UseCase → Controller`).
6. Controller calls the use case through `BaseController.doAction<T>(action:, onSuccess:,
   onError:)`, which unwraps the `Either` and manages loading/error state — don't hand-roll that.
7. **If the new endpoint is a cross-cutting concern already used by several features** (OTP
   send/verify, transaction charge quote, category list), register it once in the global
   `AppBinding` (`lib/app/app_binding.dart`) instead of duplicating it per-feature — that's the
   existing pattern for those three concerns.

---

## 6. Open items / known gaps worth knowing before building on top of this

- `merchant/`'s `GET /merchant/v1/partners` and `bill-payment/`'s `POST/PATCH
  /bill/v1/settings` have the security-config bugs noted in §1 — don't assume "listed as
  public in `SecurityConfig`" means "reachable without a role check," and vice versa.
- No shared `ApiResponse<T>` exists despite `CLAUDE.md` describing a migration toward one — plan
  API integrations per-endpoint, not against a single envelope shape.
- `accounting/` is gRPC-only and undocumented in most day-to-day discussion of "the API" — if an
  AI/ML integration needs ledger, limits, disbursement, settlement, or report data, it goes
  through gRPC to `accounting/`, not REST via Kong.
- Polygon AI (`support/`'s SSE chat) is the one existing LLM-adjacent integration in the codebase
  — worth reading `docs/support.md` before building a second one, especially the note about the
  JDK `HttpClient` being pinned to HTTP/1.1 (its default h2c upgrade silently drops POST bodies
  against the uvicorn upstream it talks to).
