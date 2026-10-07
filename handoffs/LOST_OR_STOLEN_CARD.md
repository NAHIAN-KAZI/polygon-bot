# LOST_OR_STOLEN_CARD — Integration Handoff

Freezing a lost, stolen or misused card from chat. This is one of only two
actions the chatbot performs on the bank (user-approved exception), so it is
gated by an OTP **and** the card PIN or login password. Read `COMMON.md` §5 first.

`category` / `service`: `card_services` / `frezz_unfrezz` →
`PATCH card/v1/cards/{id}/freeze` (after `POST otp/v1/send` + `POST otp/v1/verify`).

Not available in chat: reporting lost/stolen as a separate request (12.1)
and **unfreezing** — the bot says to use the app.

## Flow

1. Customer: "i lost my card" / "card churi hoye gese, block koro" /
   "Someone just used my debit card… please block it".
   The bot freezes only when the customer **asked to block** the card **or
   said what happened** to it. A vague "my card isn't working" or "reset my
   PIN" gets a question instead — never a freeze.
2. Which card: one card → used automatically; several →
   `ACCOUNT_SELECTION_REQUIRED` with card entries (`id`, masked `cardNumber`,
   `cardType`); answer with `payload: {"cardId": id}` or in words.
3. Reason: if the customer only said "block my card", the bot asks why
   (`CLARIFICATION_REQUIRED`). The stored reason is the customer's own words.
4. OTP sent → `OTP_REQUIRED` (below). The bubble text is fixed wording (security step).
5. App submits the verification form → card frozen → `BANKING_SERVICE`.

## Response — `result`

**OTP step** (live):
```json
{"type": "OTP_REQUIRED", "category": "card_services", "service": "frezz_unfrezz",
 "payload": {"cardId": "45", "cardLast4": "0293", "reason": "my card was stolen",
             "otpRequired": true, "credentialOptions": ["pin", "password"],
             "verificationStatus": "OTP_SENT"}, "routing": null}
```

**Submit** (form → structured payload, exactly one of `pin` / `password`):
```json
{"message": "Verify", "payload": {"otp": "123456", "pin": "1234"}}
```

**Frozen** (live) — only the outcome, never the bank's card record:
```json
{"type": "BANKING_SERVICE", "category": "card_services", "service": "frezz_unfrezz",
 "payload": {"executed": true, "cardId": "45", "cardLast4": "0293", "status": "BLOCKED"},
 "routing": {"action": "redirect"}}
```

**Cancelled** ("cancel" while the form is open):
`{"type": "BANKING_SERVICE", "payload": {"executed": false, "cancelled": true}}`.

Errors stay `OTP_REQUIRED` with a new `verificationStatus` (see `COMMON.md` §5):
wrong code → `OTP_INCORRECT` + `attemptsRemaining`; expired → `OTP_EXPIRED`
(new code sent); both PIN and password → `CREDENTIALS_INVALID_COMBINATION`;
too many codes → `SEND_THROTTLED` / `OTP_BLOCKED`; bank failure → `SERVICE_UNAVAILABLE`
("Your card has not been frozen").

<!-- UI-TO-BUILD:START -->
## UI to build, use case by use case

Blocks U1–U11 are defined in `COMMON.md` §11. The customer finishes everything inside the chat, as with the nickname and email change. Drive every block from `result.type`/`category`/`service`/`routing`/`payload`, never from bubble text.

| # | Use case | Outcome | What the customer sees | Buttons | Prefilled from | Calls / notes |
|---|---|---|---|---|---|---|
| 12.1 | Report lost/stolen card | Gather → inline box | Card picker if several → **U8** caution box: card (preselected), reason (lost, stolen, damaged, expired, other), a warning that the card is closed for good and a replacement issued | Report and replace · Freeze instead (sends the message `Freeze my card`) | `cardId`, `reasonCode` | U7: code + PIN or password · `POST card/v1/cards/{id}/replacement-requests` |
| 12.2 | Freeze card immediately | Executed in chat | Same as 4.1 (explicit freeze/block request) | Yes / No, Verify / Cancel | None | Same as 4.1 |

<!-- UI-TO-BUILD:END -->

## Frontend integration (Dart)

```dart
Future<void> handleFreeze(ChatTurnResult turn) async {
  final p = turn.payload ?? {};
  switch (turn.type) {
    case 'OTP_REQUIRED':
      final form = await showVerificationSheet(
        title: 'Freeze card ending ${p['cardLast4']}',
        warning: 'All transactions on this card will be blocked until you unfreeze it in the app.',
        allowPin: (p['credentialOptions'] as List).contains('pin'),
        allowPassword: (p['credentialOptions'] as List).contains('password'),
        error: switch (p['verificationStatus']) {
          'OTP_INCORRECT' => 'Wrong code. ${p['attemptsRemaining'] ?? ''} attempts left.',
          'OTP_EXPIRED' => 'Code expired — we sent a new one.',
          'CREDENTIALS_INVALID_COMBINATION' => 'Enter your PIN or your password, not both.',
          _ => null,
        },
      );
      if (form == null) return onSend('cancel');
      // Never echo these in the chat or logs.
      await onSend('Verify', payload: {
        'otp': form.otp,
        if (form.pin != null) 'pin': form.pin else 'password': form.password,
      });
    case 'BANKING_SERVICE' when p['executed'] == true:
      showSuccessBanner('Card ending ${p['cardLast4']} is frozen');
  }
}
```

## Live-verified (2026-10-03, `taslim_islamic`, dev)

- "my debit card was stolen, please freeze it" → OTP sent → form with OTP + password → card 45 ACTIVE → **BLOCKED**; restored afterwards via the bank's unfreeze endpoint (outside chat).
- "i lost my card", Banglish "card churi hoye gese, block koro", multi-line misuse story → `OTP_REQUIRED` with the customer's own reason.
- "my card isnt working", "reset my card pin" → no freeze; a question / "only in the app".
- "actually forget that, what's my balance" while the form is open → leaves the freeze step, answers the balance.

## Known gaps

1. Dev OTP accepts `0000` (no SMS). Production sends a real SMS — test the form against production OTP behaviour before go-live.
2. Multi-card selection unit-tested only (dev user has one card).
