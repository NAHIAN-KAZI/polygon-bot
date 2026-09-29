# Beneficiary List → Transfer Screen Navigation

How a beneficiary row in the Beneficiary List screen sends the user into the correct
transfer screen, and how that screen consumes the beneficiary data.

## Flow summary

```
BeneficiaryScreen (list)
   └─ tap row → _BeneficiaryTile._send()
        └─ beneficiarySendRoute(item)   // maps serviceType → route name
        └─ Get.toNamed(route, arguments: item)   // whole BeneficiaryItem passed
              ├─ AppRoutes.bankTransferPolygonBankAccount → PolygonBankAccountController
              ├─ AppRoutes.bankTransferOtherBank          → OtherBankController
              ├─ AppRoutes.walletTransferRoute(provider)  → wallet transfer controller
              └─ null (e.g. CARD_PAYMENT)                → falls back to details bottom sheet
                    destination controller.onInit():
                       if (Get.arguments is BeneficiaryItem) applyBeneficiary(Get.arguments)
                       → prefills fields, re-validates account via live lookup API
```

## Get-list call

- Use case: `GetBeneficiariesUseCase` → `BeneficiaryRepository.getBeneficiaries()`
- Impl chain: `BeneficiaryCacheImpl` (persists to `PreferenceCache` on success) →
  `BeneficiaryHttpImpl._fetchList()` → `client.authorizedGet(ApiUrl.beneficiariesUrl)`
- Endpoint: `GET {bankingBaseUrl}beneficiary/v1/beneficiaries`
  (server-filtered variant: `getBeneficiariesByServiceType()` adds `?serviceType=OWN_BANK|OTHER_BANK|MFS|...`)
- Loaded in `BeneficiaryListController.loadBeneficiaries()` (called from `onInit()`),
  populates `RxList<BeneficiaryItem> beneficiaries`.

## Files

| Concern | Path |
|---|---|
| List screen (UI) | `lib/features/beneficiary/presentation/screens/beneficiary_screen.dart` |
| List controller | `lib/features/beneficiary/presentation/controller/beneficiary_list_controller.dart` |
| Binding | `lib/features/beneficiary/presentation/bindings/beneficiary_binding.dart` |
| Domain entity | `lib/features/beneficiary/domain/entity/beneficiary_item.dart` |
| Wire DTO | `lib/features/beneficiary/data/model/beneficiary_dto.dart` |
| Repository interface | `lib/features/beneficiary/domain/repo/beneficiary_repository.dart` |
| HTTP impl (API call) | `lib/features/beneficiary/data/repo_impl/beneficiary_http_impl.dart` |
| Cache impl | `lib/features/beneficiary/data/repo_impl/beneficiary_cache_impl.dart` |
| Get-list use case | `lib/features/beneficiary/domain/usecase/get_beneficiaries_use_case.dart` |
| **Route-resolution helper** | `lib/features/beneficiary/presentation/utils/beneficiary_send_route.dart` |
| Route registration (beneficiary) | `lib/features/beneficiary/presentation/pages.dart` |
| Embeddable widget (top-of-transfer-screen) | `lib/features/beneficiary/presentation/widgets/beneficiary_row.dart` |
| Route registration (transfer) | `lib/features/bank_transfer/presentation/pages.dart` |
| Route constants | `lib/res/routes/app_routes.dart` |
| Route aggregation | `lib/res/routes/app_pages.dart` |

Transfer destinations (own-bank / other-bank shown as reference examples — wallet/education/etc.
follow the same `onInit → applyBeneficiary` pattern):

| Screen | UI | Controller |
|---|---|---|
| Polygon Bank Account | `lib/features/bank_transfer/presentation/polygon_bank_account/polygon_bank_account_screen.dart` | `.../polygon_bank_account_controller.dart` |
| Other Bank | `lib/features/bank_transfer/presentation/other_bank/other_bank_screen.dart` | `.../other_bank_controller.dart` |

Binding: `lib/features/bank_transfer/presentation/bindings/bank_transfer_binding.dart`

## Tap handler — the navigation call

`beneficiary_screen.dart` (`_BeneficiaryTile`):

```dart
onTap: () => _send(),

void _send() {
  final route = beneficiarySendRoute(item);
  if (route == null) {
    _showDetails(Get.context!);   // e.g. CARD_PAYMENT: no deterministic destination
    return;
  }
  Get.toNamed(route, arguments: item);   // passes the FULL BeneficiaryItem, not just an id
}
```

The "⋮" menu on the same row opens `showBeneficiaryDetailsSheet(...)` (edit/delete) —
deliberately separate from tap-to-send.

## Route resolution — `beneficiary_send_route.dart`

```dart
String? beneficiarySendRoute(BeneficiaryItem item) {
  switch (item.serviceType) {
    case BeneficiaryServiceType.ownBank:
      return AppRoutes.bankTransferPolygonBankAccount;
    case BeneficiaryServiceType.otherBank:
      return AppRoutes.bankTransferOtherBank;
    case BeneficiaryServiceType.mfs:
      final provider = item.mfsProvider;
      return provider == null ? null : AppRoutes.walletTransferRoute(provider.toLowerCase());
    case BeneficiaryServiceType.cardPayment:
      return null;   // no sub-type/providerId to pick a leaf route → falls back to details sheet
    ...
  }
}
```

Route constants (`app_routes.dart`):

```dart
static const String bankTransferPolygonBankAccount = '/bank_transfer/polygon_bank_account';
static const String bankTransferOtherBank = '/bank_transfer/other_bank';
static const String walletTransferPattern = '/wallet_transfer/:provider';
static String walletTransferRoute(String providerId) => '/wallet_transfer/$providerId';
static const String beneficiary = '/beneficiary';
static const String beneficiaryForm = '/beneficiary/form';
```

## Destination side — consuming `Get.arguments`

Both transfer controllers check for a `BeneficiaryItem` in `onInit()`:

```dart
// polygon_bank_account_controller.dart
if (Get.arguments is BeneficiaryItem) {
  applyBeneficiary(Get.arguments as BeneficiaryItem);
}

void applyBeneficiary(BeneficiaryItem item) {
  sendToMode.value = item.identifierType == 'MOBILE' ? 'mobile' : 'account';
  identifierController.text = item.accountNumber;
  onIdentifierChanged(item.accountNumber);   // re-runs the live account lookup, same as manual entry
  selectedBeneficiaryId.value = item.id;
  _beneficiaryNickname = item.nickname;
  _beneficiaryPhotoUrl = item.photoUrl;
}
```

`other_bank_controller.dart` mirrors this and additionally applies `bankName`, `district`,
`branchName`, `routingNumber` — each guarded against the screen's hardcoded dropdown option
lists (`bangladeshBanks.contains(item.bankName) ? item.bankName : null`, etc.) to avoid a
`DropdownButton` crash on a stale/mismatched value.

`selectedBeneficiaryId` is later checked at submit time to decide whether to offer "Save
Beneficiary" on the success screen — skipped when the transfer was already sent to a saved
beneficiary.

## Folder structure (feature-first)

```
lib/features/beneficiary/
├── data/
│   ├── model/beneficiary_dto.dart
│   └── repo_impl/
│       ├── beneficiary_cache_impl.dart
│       └── beneficiary_http_impl.dart          # GET/POST/PATCH/DELETE /beneficiary/v1/beneficiaries
├── domain/
│   ├── entity/
│   │   ├── beneficiary_item.dart               # BeneficiaryItem
│   │   ├── beneficiary_service_type.dart       # enum used for routing
│   │   └── ...
│   ├── repo/beneficiary_repository.dart
│   └── usecase/get_beneficiaries_use_case.dart, get_beneficiaries_by_service_type_use_case.dart, ...
└── presentation/
    ├── bindings/beneficiary_binding.dart
    ├── controller/beneficiary_list_controller.dart
    ├── screens/beneficiary_screen.dart
    ├── utils/beneficiary_send_route.dart        # list-item → route mapping
    ├── widgets/beneficiary_row.dart, beneficiary_details_sheet.dart, ...
    └── pages.dart                                # GetPage route registration

lib/features/bank_transfer/
├── data/repo_impl/bank_transfer_http_impl.dart, bank_transfer_cache_impl.dart
├── domain/usecase/transfer_polygon_account, transfer_other_bank, get_beneficiary_info, ...
└── presentation/
    ├── bindings/bank_transfer_binding.dart
    ├── polygon_bank_account/polygon_bank_account_controller.dart, _screen.dart
    ├── other_bank/other_bank_controller.dart, _screen.dart
    └── pages.dart
```

## Gotchas

1. **Navigation passes the whole entity**, not an id — destination reads `Get.arguments is BeneficiaryItem`.
2. **CARD_PAYMENT has no deterministic destination** (`beneficiarySendRoute` → `null`) since it carries no sub-type to pick among its leaf routes; UI falls back to the details sheet.
3. **MFS/other parametrized routes** depend on `item.mfsProvider` / `item.providerId` being non-null — null-safety on these fields gates whether navigation is even possible.
4. Destination controllers **re-verify via a live lookup** rather than trusting cached beneficiary data, and **guard dropdown-bound fields** against stale values.
5. Both `BeneficiaryBinding` and `BankTransferBinding` independently register the beneficiary DI chain (GetX `fenix: true`), so the embedded `BeneficiaryRow` widget on transfer screens works even if the user never opened the standalone Beneficiary screen.
