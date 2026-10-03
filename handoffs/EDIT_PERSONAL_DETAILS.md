# EDIT_PERSONAL_DETAILS — Integration Handoff

Viewing the customer's profile, address/KYC, registered contacts, and the
status of their change requests. **Changing** anything is not possible in chat
— the bot says so and points to the app. Read `COMMON.md` first.

## Services

| Ask | `category` / `service` | Bank endpoint | Status |
|---|---|---|---|
| Profile (7.1) | `profile` / `profile` | `GET auth/v1/user` | ✅ Live |
| Address / KYC (7.7) | `profile` / `address` | `GET customer/v1/me/demographic` | ✅ Live |
| Registered contacts (7.10) | `profile` / `contacts` | `GET customer/v1/me/contacts` | ✅ Live |
| Profile change requests (7.12) | `profile` / `profile_change_requests` | `GET service-request/v1/profile-changes` | ✅ Live |
| Contact priority requests (7.14) | `profile` / `contact_priority_requests` | `GET service-request/v1/contact-priority` | ✅ Live |

Blocked (bot: "can't be done in this chat, you can do it in the app"):
nickname, profile image, mobile, email, address, KYC submit, change/priority submits.

## How to trigger

Live-tested: "profile", "my address", "which phone numbers are registered",
"did my profile change request get approved",
"change my email to new@example.com" (→ app), "update my address please" (→ shows the address on file; never claims an update).

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
  }
}
```

Rendering: profile and address as cards with an "Edit in app" button (the only
way to change them); request lists as status rows.

## Live-verified (2026-10-03, `taslim_islamic`)

- "profile" → name, email, masked phone.
- "my address" → "Your present address is not set." (KYC pending).
- "which phone numbers are registered" → `contacts`, none.
- "change my email to new@example.com" → "…You can update this information through our mobile banking app."

## Known gaps

1. "change my email…" is routed to the change-request list (reply is still right: "do it in the app"); a dedicated "not available here" reply would be cleaner.
2. Non-empty contacts/requests not seen live.
