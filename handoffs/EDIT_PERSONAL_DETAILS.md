# EDIT_PERSONAL_DETAILS — Integration Handoff

Viewing the customer's profile, address/KYC, registered contacts and the
status of their change requests, plus the approved in-chat changes: nickname and
address (after a yes), mobile number and email (after a verification code).
Everything else is an `APP_ACTION` or a redirect. Read `COMMON.md` first (§5, §7, §8).

## Services

| Ask | `category` / `service` | Bank endpoint | Status |
|---|---|---|---|
| Profile (7.1) | `profile` / `profile` | `GET auth/v1/user` | ✅ Live |
| Address / KYC (7.7) | `profile` / `address` | `GET customer/v1/me/demographic` | ✅ Live |
| Registered contacts (7.10) | `profile` / `contacts` | `GET customer/v1/me/contacts` | ✅ Live |
| Profile change requests (7.12) | `profile` / `profile_change_requests` | `GET service-request/v1/profile-changes` | ✅ Live |
| Contact priority requests (7.14) | `profile` / `contact_priority_requests` | `GET service-request/v1/contact-priority` | ✅ Live |

| Change nickname (7.2) | `profile_update` / `update_nickname` | `PATCH auth/v1/user/profile/nickname` | ✅ Built (yes/no); live test pending |
| Change address (7.8) | `profile_update` / `update_address` | `PATCH customer/v1/me/demographic` | ✅ Built (yes/no); live test pending |
| Change mobile (7.5) | `profile_update` / `update_mobile` | `POST otp/v1/send` + `otp/v1/verify`, `POST auth/v1/auth/mobile/update` | ✅ Built (code); live test pending |
| Change email (7.6) | `profile_update` / `update_email` | `POST otp/v1/send` + `otp/v1/verify`, `POST auth/v1/auth/email/update` | ✅ Built (code); live test pending |
| Profile photo (7.3/7.4) | `profile_update` / `update_profile_image` | none | ✅ Redirect (`routing.action: "update_profile_image"`) |
| KYC, profile change request, primary contact (7.9/7.11/7.13) | `app_actions` / `kyc_submit`, `profile_change_request`, `contact_priority_change` | none | ✅ App action |

## What the bot does for each request in this intent

| Row | Request | Outcome |
|---|---|---|
| 7.1 | Get profile | Handled in chat: `profile` / `profile` |
| 7.2 | Update nickname | Executed in chat after yes/no: `profile_update` / `update_nickname` (`payload.nickName`) |
| 7.3/7.4 | Upload / change profile image | Redirect, no bank call: `BANKING_SERVICE`, `profile_update` / `update_profile_image`, `payload: {"executed": false}`, `routing.action: "update_profile_image"` (photos are chosen in the app) |
| 7.5 | Update mobile number | Executed in chat after a code: `profile_update` / `update_mobile` (`OTP_REQUIRED`, code only, sent to the **current** registered phone). The customer is signed out afterwards |
| 7.6 | Update email address | Executed in chat after a code: `profile_update` / `update_email` (`OTP_REQUIRED`, code only, sent to the current registered phone) |
| 7.7 | Get address | Handled in chat: `profile` / `address` |
| 7.8 | Update address | Executed in chat after yes/no: `profile_update` / `update_address` (any of `presentAddress`, `permanentAddress`, `district`, `division`) |
| 7.9 | Submit KYC | App action `kyc_submit` → `UpdateKycScreen`, `/profile/update_kyc` (Open). Prefill: `occupation` |
| 7.10 | My contacts | Handled in chat: `profile` / `contacts` |
| 7.11 | Profile change request — submit | App action `profile_change_request` → `ProfileChangeRequestScreen`, `/profile_change_request` (Open). Prefill: `fieldName`, `requestedValue`, `reason` |
| 7.12 | Profile change requests — list | Handled in chat: `profile` / `profile_change_requests` |
| 7.13 | Contact priority — submit | App action `contact_priority_change` → `ContactPriorityScreen`, `/contact_priority` (Open). Prefill: `reason` |
| 7.14 | Contact priority requests — list | Handled in chat: `profile` / `contact_priority_requests` |

Values that fail a format check (an email without `@`, a mobile number that isn't
11 digits starting `01`, a nickname over 50 characters) are dropped and asked for again
(`CLARIFICATION_REQUIRED`) before any yes/no or code.

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| 7.1 | Get profile | Answered in chat | **U3 profile** — Name, nickname, contact info. CIF and NID are already redacted: do not request them. | None | None | — |
| 7.2 | Update nickname | Executed in chat | **U6** (new nickname) → done notice. Refresh the cached profile nickname afterwards | Yes / No | None | The bot makes the call |
| 7.3/7.4 | Upload profile image | Gather → inline box | **U8** photo box: choose a photo (camera or gallery) and upload | Choose photo · Upload | None | None · `PATCH auth/v1/user/profile/image` (multipart) |
| 7.5 | Update mobile number | Executed in chat | **U7** (code only, shows the new number) → done notice. The bank signs the session out after the change: send the customer to login | Verify / Cancel | None | The bot makes the call after the code |
| 7.6 | Update email address | Executed in chat | **U7** (code only, shows the new email) → done notice | Verify / Cancel | None | The bot makes the call after the code |
| 7.7 | Get address | Answered in chat | **U3 address** — Present and permanent address. | None | None | — |
| 7.8 | Update address | Executed in chat | **U6** (the address fields that will change) → done notice | Yes / No | None | The bot makes the call |
| 7.9 | Submit KYC | App action → inline box | **U8** box: Box with three photo slots (NID front, NID back, signature: camera or gallery) and optional occupation and income fields. After the button: None. | Submit | `occupation` (from `ui.prefill`) | App calls `POST customer/v1/me/kyc` (multipart); shows a local done/failed tile |
| 7.10 | My contacts | Answered in chat | **U2 contacts** — Registered phones and emails. | None | None | — |
| 7.11 | Profile change — submit | App action → inline box | **U8** box: Form: detail to change (mobile, email, NID, legal name, date of birth), new value, reason. After the button: U7: code (SMS or email). | Submit request | `fieldName`, `requestedValue`, `reason` (from `ui.prefill`) | App calls `POST service-request/v1/profile-changes`; the bank reviews it; shows a local done/failed tile |
| 7.12 | Profile change — list | Answered in chat | **U2 requests** — Profile-change requests with status. | None | None | — |
| 7.13 | Contact priority — submit | App action → inline box | **U8** box: The registered phones and emails to choose the primary one, plus a reason. After the button: U7: code. | Submit request | `reason` (from `ui.prefill`) | App calls `POST service-request/v1/contact-priority`; shows a local done/failed tile |
| 7.14 | Contact priority — list | Answered in chat | **U2 requests** — Primary-contact change requests with status. | None | None | — |

<!-- UI-TO-BUILD:END -->

## How to trigger

Live-tested: "profile", "my address", "which phone numbers are registered",
"did my profile change request get approved".
Changes: "change my nickname to Tas", "update my present address to House 5, Road 2, Banani",
"change my email to new@example.com", "change my mobile number to 01711223344".
Their outcomes are in the table above.

## Response — `result.payload` (live)

**profile** — the customer's own record, passed through for the app. Show the
fields you need; mask the phone. (The bot's own reply never mentions CIF/NID.)
```json
{"id": 66, "name": "taslim_islamic", "nickName": "taslim_islamic", "username": "taslim_islamic",
 "email": "taslim.islamic@gmail.com", "phone": "01311111110", "bankingMode": "ISLAMIC",
 "cif": "109260000202", "status": "ACTIVE", "transactionPinSet": true, "profileImage": null,
 "createdAt": "2026-09-23T15:04:40+06:00", "lastLoginAt": "2026-10-04T03:44:09+06:00"}
```

**address**:
```json
{"status": "success", "data": {"presentAddress": null, "permanentAddress": null,
  "district": null, "division": null, "occupation": null, "kycStatus": "PENDING",
  "kycRejectionReason": null, "preferredBankingMode": null}}
```

**contacts**: `{"status": "success", "data": []}` ·
**profile_change_requests / contact_priority_requests**: `{"requests": []}`.

**Nickname / address** yes/no step (`COMMON.md` §7):
```json
{"type": "CONFIRMATION_REQUIRED", "category": "profile_update", "service": "update_nickname",
 "payload": {"nickName": "Tas"}}
```
Yes → `BANKING_SERVICE` with the bank's response plus `executed: true`,
`routing.action: "redirect"`. No → `{"executed": false, "cancelled": true}`.
A bank refusal → `SERVICE_UNAVAILABLE`. The bank once answered an address PATCH with a 409 even though
it saved, so after a refusal re-read the address before showing a result.

**Email / mobile** code step:
```json
{"type": "OTP_REQUIRED", "category": "profile_update", "service": "update_email",
 "payload": {"newEmail": "new@example.com", "otpRequired": true, "credentialOptions": [],
             "verificationStatus": "OTP_SENT"}}
```
Submit `{"message": "Verify", "payload": {"otp": "<code>"}}`. Done →
`BANKING_SERVICE` `{"executed": true, "newEmail": ...}` (or `newPhone`). Refused by the bank →
`BANKING_SERVICE` `{"executed": false, "bankMessage": "..."}`. Too many codes →
`{"executed": false, "verificationStatus": "SEND_THROTTLED"}`.

**Profile photo**:
```json
{"type": "BANKING_SERVICE", "category": "profile_update", "service": "update_profile_image",
 "payload": {"executed": false},
 "routing": {"category": "profile_update", "service": "update_profile_image", "subservice": null,
             "action": "update_profile_image"}}
```

## Frontend integration (Dart)

```dart
void renderProfile(ChatTurnResult turn) {
  final p = turn.payload ?? {};
  switch (turn.service) {
    case 'profile':
      showProfileCard(
        name: p['name'], username: p['username'], email: p['email'],
        phone: maskTail(p['phone'], keep: 4), bankingMode: p['bankingMode'],
        onEdit: () => openAppScreen('edit_profile'),
      );
    case 'address':
      final a = (p['data'] as Map).cast<String, dynamic>();
      showAddressCard(present: a['presentAddress'], permanent: a['permanentAddress'],
          kycStatus: a['kycStatus'], onEdit: () => openAppScreen('edit_address'));
    case 'contacts':
      final items = (p['data'] as List);
      if (items.isNotEmpty) showContactList(items.cast<Map<String, dynamic>>());
    case 'profile_change_requests':
    case 'contact_priority_requests':
      final reqs = (p['requests'] as List);
      if (reqs.isNotEmpty) showRequestStatusList(reqs.cast<Map<String, dynamic>>());
    case 'update_profile_image':
      showOpenInAppChip('Change photo', onTap: () => openAppScreen('update_profile_image'));
    case 'update_nickname':
    case 'update_address':
    case 'update_email':
    case 'update_mobile':
      if (p['executed'] == true) {
        refreshProfileFromBank();               // show the saved values, not the bubble
        if (turn.service == 'update_mobile') signOutAfterMobileChange();
      }
  }
}
// CONFIRMATION_REQUIRED, OTP_REQUIRED (code only: credentialOptions is []) and
// APP_ACTION (KYC, profile change request, primary contact) use the shared cases in COMMON.md §10.
```

Rendering: profile and address as cards with an "Edit in app" button; request lists
as status rows; an executed change as a short success tile built from the refreshed profile.

## Live-verified (2026-10-03, `taslim_islamic`)

- "profile" → name, email, masked phone.
- "my address" → "Your present address is not set." (KYC pending).
- "which phone numbers are registered" → `contacts`, none.
- 2026-10-06 live run (nothing confirmed or submitted): nickname, photo and KYC asks reached
  their step in 3 of 5 phrasings each; mobile, email and address asks mostly got a clarifying question first.

## Known gaps

1. Nickname, address, email and mobile changes are built and unit-tested, but **not yet live-verified** end to end.
2. Mobile, email and address requests often get a clarifying question before the yes/no or code step (2026-10-06 live run).
3. Non-empty contacts/requests not seen live.
