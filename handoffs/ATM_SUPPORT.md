# ATM_SUPPORT — Integration Handoff

Covers the one real, read-only piece of ATM_SUPPORT implemented so far:
listing the customer's disputes. Base connection details (URL, auth header,
SSE event shapes) are in the main `HANDOFF.md`/`INTEGRATION.md` — this doc
only covers what's specific here.

**Scope note**: ATM_SUPPORT has 3 endpoints total per the bank's own cURL
reference — cash-by-code (2.1, mutating) and raise-dispute (2.2, mutating)
are both blocked under the standing GET-only policy, pending a future
gather+redirect implementation (see TASKS.md T-61, queued — raise-dispute
will gather details and redirect to the real Dispute a Transaction screen,
never submit it itself). This doc covers only 2.3, "list disputes" — the
only piece actually built.

## How to trigger it

- Natural language: "show my disputes", "what disputes have I filed",
  "list my open disputes".
- Direct route: `{"category":"service_requests","service":"disputes"}`.

Note the wire category is `service_requests`, not `atm_support` — this
service doesn't exist in the bank's live navigable taxonomy at all (it's a
backend-only service-request listing, confirmed by checking a live taxonomy
fetch directly), so it's a synthetic addition (ADR-0011 amendment,
2026-10-01). The same endpoint/adapter is reused by CARD_ISSUE (3.4) and
FAILED_TRANSFER (8.3) per the bank's own doc — those two intents' chatbot
routing isn't wired yet, but the underlying data layer is already shared and
ready.

## Request payload

No payload required — resolves the customer's account number internally
(same `_resolve_account_number` helper every other account-scoped service
uses).

## Response — `result` event

```json
{"type": "BANKING_SERVICE", "category": "service_requests", "service": "disputes",
 "payload": {"disputes": []}}
```
`disputes` is an array, empty if the customer has none open — this is the
normal, common case, not an error state.

## Frontend integration (Dart)

Same SSE parsing pattern as every other intent (see `ACCOUNT_INFO.md` for
the full snippet) — this one only needs its own `case` inside the result
switch:

```dart
case 'service_requests':
  if (result['service'] == 'disputes') {
    final disputes = (result['payload']['disputes'] as List)
        .cast<Map<String, dynamic>>();
    if (disputes.isEmpty) {
      renderEmptyState('No open disputes.');
    } else {
      renderDisputeList(disputes);
    }
  }
  break;
```

**Rendering recommendation**: a simple list, one row per dispute. The exact
field shape of a real (non-empty) dispute entry hasn't been observed live
yet (this test account has none) — when the frontend team gets a real
non-empty response, confirm the entry shape matches what `service-request/v1/disputes`
documents before finalizing the row layout.

**Action buttons**: none for listing. Once T-61 (raise-dispute,
gather+redirect) lands, that flow will carry its own `routing.action`
pointing at the real "Dispute a Transaction" screen — not yet implemented,
don't build against it yet.

## Live-verified (2026-10-01)

- "show my disputes" → `BANKING_SERVICE`/`service_requests`/`disputes`, real (empty) response.
- "list my open disputes" → same, confirmed reliable across repeated trials after a related classifier fix (T-59) — this exact phrasing was briefly affected by an unrelated regression (session-context bleed from a prior `ACCOUNT_SELECTION_REQUIRED` state into an unrelated transfer clarification), now fixed and reverified.

## Known gaps

1. Cash-by-code (2.1) and raise-dispute (2.2) — both still blocked, no implementation yet. Raise-dispute is queued (T-61) as gather+redirect only (never submits).
2. Real (non-empty) dispute entry shape not yet observed live — confirm field names before building the detail-row UI.
3. CARD_ISSUE (3.4) and FAILED_TRANSFER (8.3) share this exact same endpoint/data but aren't wired into chatbot classification for those intents yet — quick follow-up once prioritized, the adapter itself needs no changes.
